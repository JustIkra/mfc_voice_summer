from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryCallRepository,
    InMemoryFinalReportRepository,
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
from call_analytics.service.ports import RecordingWorkspace, Transcriber
from domain import (
    AudioBlob,
    CallRecording,
    ChannelLayout,
    JobStatus,
    RecordingId,
    Transcript,
)
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


class EmptyTranscriber(Transcriber):
    async def transcribe(self, recording_id: RecordingId, audio: AudioBlob) -> Transcript:
        return Transcript(recording_id=recording_id, language="ru", segments=(), full_text="")


class TrackingWorkspace(RecordingWorkspace):
    def __init__(self) -> None:
        self.cleared: list[RecordingId] = []

    async def prepare(self, call_id, parts):
        raise AssertionError("prepare is not used by pipeline tests")

    async def load_audio(self, call_id):
        raise AssertionError("load_audio is not used by pipeline tests")

    async def clear(self, call_id: RecordingId) -> None:
        self.cleared.append(call_id)

    async def clear_stale(self, older_than, protected=()):
        raise AssertionError("clear_stale is not used by pipeline tests")


def _service(
    jobs,
    artifacts,
    transcriber=None,
    *,
    calls=None,
    final_reports=None,
    workspace=None,
):
    return CallProcessingService(
        source=FakeRecordingSource({RID.value: stereo_blob()}),
        transcriber=transcriber or NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: NOW,
        calls=calls,
        final_reports=final_reports,
        workspace=workspace,
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


async def test_empty_transcript_marks_call_skipped_and_clears_workspace() -> None:
    jobs = InMemoryJobRepository()
    artifacts = InMemoryArtifactStore()
    calls = InMemoryCallRepository()
    workspace = TrackingWorkspace()
    service = _service(
        jobs,
        artifacts,
        transcriber=EmptyTranscriber(),
        calls=calls,
        workspace=workspace,
    )
    job = await service.enqueue(_recording())
    await calls.register(_recording(), job)

    processed = await service.process(RID)

    assert processed.status is JobStatus.SKIPPED_EMPTY
    assert await calls.status(RID) is JobStatus.SKIPPED_EMPTY
    assert workspace.cleared == [RID]


async def test_success_finalizes_document_and_clears_workspace() -> None:
    jobs = InMemoryJobRepository()
    artifacts = InMemoryArtifactStore()
    calls = InMemoryCallRepository()
    final_reports = InMemoryFinalReportRepository(jobs)
    workspace = TrackingWorkspace()
    service = _service(
        jobs,
        artifacts,
        calls=calls,
        final_reports=final_reports,
        workspace=workspace,
    )
    job = await service.enqueue(_recording())
    await calls.register(_recording(), job)

    processed = await service.process(RID)

    assert processed.status is JobStatus.DONE
    assert await final_reports.load_payload(RID) is not None
    assert workspace.cleared == [RID]
