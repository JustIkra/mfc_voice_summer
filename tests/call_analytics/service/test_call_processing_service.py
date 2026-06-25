from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
)
from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from call_analytics.infra.ports import TranscriberError
from call_analytics.service import CallProcessingService
from domain import CallRecording, ChannelLayout, JobStatus, RecordingId
from tests.call_analytics.service.conftest import (
    FailingTranscriber,
    FakeRecordingSource,
    stereo_blob,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 1, 10, 12, 0, tzinfo=MSK)
RID = RecordingId("rec-1")


def _recording() -> CallRecording:
    return CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=5),
        channel_layout=ChannelLayout.STEREO,
    )


def _service(jobs, artifacts, transcriber=None):
    return CallProcessingService(
        source=FakeRecordingSource({RID.value: stereo_blob()}),
        transcriber=transcriber or NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: NOW,
    )


async def test_process_runs_pipeline_to_done_and_writes_report() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    service = _service(jobs, artifacts)

    await service.enqueue(_recording())
    job = await service.process(RID)

    assert job.status is JobStatus.DONE
    assert await artifacts.load_transcript(RID) is not None
    assert await artifacts.load_diarization(RID) is not None
    assert await artifacts.load_emotion(RID) is not None
    assert await artifacts.load_report(RID) is not None


async def test_run_next_stage_is_idempotent_for_completed_stage() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    service = _service(jobs, artifacts)
    job = await service.enqueue(_recording())

    job = await service.run_next_stage(job.id)
    assert job.status is JobStatus.PENDING
    transcript = await artifacts.load_transcript(RID)

    job = await service.run_next_stage(job.id)
    assert await artifacts.load_transcript(RID) == transcript


async def test_failed_stage_then_retry_recomputes_only_failed_stage() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    failing = FailingTranscriber(
        error=TranscriberError.timeout("медленно"), then=NoopTranscriber(RID)
    )
    service = _service(jobs, artifacts, transcriber=failing)
    await service.enqueue(_recording())

    job = await service.process(RID)
    assert job.status is JobStatus.FAILED
    assert job.last_error is not None and job.last_error[0] == "TIMEOUT"
    assert await artifacts.load_transcript(RID) is None

    job = await service.retry(job.id)
    job = await service.process(RID)
    assert job.status is JobStatus.DONE
    assert failing.calls == 2
    assert await artifacts.load_report(RID) is not None


async def test_unexpected_programming_error_is_not_recorded_as_stage_failure() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    service = _service(
        jobs,
        artifacts,
        transcriber=FailingTranscriber(
            error=AssertionError("bug in adapter"),
            then=NoopTranscriber(RID),
        ),
    )
    await service.enqueue(_recording())

    with pytest.raises(AssertionError, match="bug in adapter"):
        await service.process(RID)
