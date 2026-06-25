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
from call_analytics.service.ports import CallProcessingPipeline
from domain import (
    AudioBlob,
    CallProcessingJob,
    CallRecording,
    ChannelLayout,
    JobStage,
    JobStatus,
    RecordingId,
)
from tests.call_analytics.service.conftest import FakeRecordingSource

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 6, 25, 12, 0, tzinfo=MSK)
RID = RecordingId("rec-queue")


class FailingPipeline(CallProcessingPipeline):
    async def enqueue(self, recording: CallRecording) -> CallProcessingJob:
        raise AssertionError("enqueue is not used")

    async def run_next_stage(self, job_id: str) -> CallProcessingJob:
        raise AssertionError("run_next_stage is not used")

    async def process(self, recording_id: RecordingId) -> CallProcessingJob:
        raise RuntimeError("boom")

    async def retry(self, job_id: str) -> CallProcessingJob:
        raise AssertionError("retry is not used")


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
    worker = ProcessingWorker(queue=queue, pipeline=pipeline, jobs=jobs)
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


async def test_worker_rejects_message_when_pipeline_raises_unexpected_error() -> None:
    queue = InMemoryProcessingQueue()
    await queue.publish(RID)
    worker = ProcessingWorker(
        queue=queue,
        pipeline=FailingPipeline(),
        jobs=InMemoryJobRepository(),
        requeue_failed=False,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await worker.run_once()

    assert queue.acked == ()
    assert queue.rejected == ((RID.value, False),)


async def test_worker_recovers_running_jobs_left_by_restart() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    pipeline = CallProcessingService(
        source=FakeRecordingSource(
            {RID.value: AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)}
        ),
        transcriber=NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=InMemoryArtifactStore(),
        clock=lambda: NOW,
    )
    running = CallProcessingJob.create(RID.value, RID, NOW).start_stage(JobStage.TRANSCRIBE)
    await jobs.save(running)
    worker = ProcessingWorker(queue=queue, pipeline=pipeline, jobs=jobs)

    recovered_count = await worker.recover_interrupted_jobs()

    job = await jobs.get(RID.value)
    message = await queue.get()
    assert recovered_count == 1
    assert job is not None
    assert job.status is JobStatus.PENDING
    assert message is not None
    assert message.recording_id == RID
