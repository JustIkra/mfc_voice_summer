from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.sqlite import SqliteCallRepository, SqliteDatabase
from domain import (
    CallerIdentity,
    CallerNameSource,
    CallProcessingJob,
    CallRecording,
    ChannelLayout,
    DiscoveredCall,
    JobStage,
    JobStatus,
    OperatorIdentity,
    QueueIdentity,
    RecordingId,
    SourceRecordingIdentity,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=MSK)
RID = RecordingId("cdr:group-001")


def _recording() -> CallRecording:
    return CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(seconds=91),
        channel_layout=ChannelLayout.MONO,
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=CallerIdentity(
            id="79001234567",
            name="Анна",
            name_source=CallerNameSource.CDR,
            name_confidence=1.0,
        ),
        operator=OperatorIdentity(id=14, extension="11198", name="Оператор"),
        source_recording=SourceRecordingIdentity(
            acct_id="901",
            filenames=("2026-08/call.wav",),
        ),
    )


def _repository(tmp_path: Path) -> SqliteCallRepository:
    database = SqliteDatabase(tmp_path / "calls.sqlite3")
    database.migrate()
    return SqliteCallRepository(database)


async def test_register_is_idempotent_and_persists_operator(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    recording = _recording()
    job = CallProcessingJob.create(recording.id.value, recording.id, NOW)

    first = await repository.register(recording, job)
    second = await repository.register(recording, job)
    loaded = await repository.load_recording(recording.id)

    assert first is True
    assert second is False
    assert loaded == recording
    assert await repository.contains(recording.id) is True


async def test_job_repository_round_trips_attempts_and_error(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    recording = _recording()
    job = CallProcessingJob.create(recording.id.value, recording.id, NOW)
    await repository.register(recording, job)
    failed = job.start_stage(JobStage.TRANSCRIBE).fail_stage(
        JobStage.TRANSCRIBE,
        "TIMEOUT",
        "model timeout",
    )

    await repository.save(failed)

    assert await repository.get(job.id) == failed
    assert list(await repository.list_by_status(JobStatus.FAILED)) == [failed]
    assert await repository.status(recording.id) is JobStatus.FAILED


async def test_discovery_can_be_saved_as_skipped_without_audio_layout(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovered = DiscoveredCall(
        id=RID,
        started_at=NOW,
        duration=timedelta(seconds=3),
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=CallerIdentity(id="79001234567"),
        operator=OperatorIdentity(id=14, extension="11198", name="Оператор"),
        source_recording=SourceRecordingIdentity(acct_id="901"),
    )

    await repository.register_skipped(discovered, "recording file is absent", NOW)

    assert await repository.contains(RID) is True
    assert await repository.status(RID) is JobStatus.SKIPPED_EMPTY
    assert await repository.load_recording(RID) is None


async def test_only_retryable_failed_calls_below_cap_are_listed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    recording = _recording()
    job = CallProcessingJob.create(recording.id.value, recording.id, NOW)
    await repository.register(recording, job)
    failed = job.start_stage(JobStage.TRANSCRIBE).fail_stage(
        JobStage.TRANSCRIBE,
        "TIMEOUT",
        "model timeout",
    )
    await repository.save(failed)

    retryable = await repository.list_retryable(max_attempts=5)

    assert list(retryable) == [recording]
    assert list(await repository.list_retryable(max_attempts=1)) == []


async def test_archive_failure_is_retryable_without_stage_attempt(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    recording = _recording()
    failed = CallProcessingJob.create(recording.id.value, recording.id, NOW).fail_before_processing(
        "ARCHIVE_IO",
        "archive write failed",
    )
    await repository.register(recording, failed)

    retryable = await repository.list_retryable(max_attempts=5)

    assert list(retryable) == [recording]
