from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
    InMemoryProcessingQueue,
)
from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from call_analytics.service import CallProcessingService, ProcessingWorker
from domain import AudioBlob, CallRecording, ChannelLayout, JobStatus, RecordingId
from tests.call_analytics.service.conftest import FakeRecordingSource

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 6, 25, 12, 0, tzinfo=MSK)
RID = RecordingId("rec-queue")


async def test_worker_processes_queue_message_and_acknowledges_done_job() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    artifacts = InMemoryArtifactStore()
    pipeline = CallProcessingService(
        source=FakeRecordingSource(
            {RID.value: AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)}
        ),
        transcriber=NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: NOW,
    )
    worker = ProcessingWorker(queue=queue, pipeline=pipeline)
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=1),
        channel_layout=ChannelLayout.STEREO,
    )

    await pipeline.enqueue(recording)
    await queue.publish(RID)
    processed = await worker.run_once()

    job = await jobs.get(RID.value)
    assert processed is True
    assert job is not None
    assert job.status is JobStatus.DONE
    assert queue.acked == (RID.value,)
    assert queue.rejected == ()
