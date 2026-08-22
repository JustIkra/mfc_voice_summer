from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.sqlite import (
    SqliteCallRepository,
    SqliteDatabase,
    SqliteFinalReportRepository,
)
from domain import (
    STAGE_ORDER,
    CallerIdentity,
    CallProcessingJob,
    CallRecording,
    CallReport,
    ChannelLayout,
    DiarizedTranscript,
    EmotionAnalysis,
    FinalReportDocument,
    JobStatus,
    OperatorIdentity,
    QuestionResolution,
    QueueIdentity,
    RecordingId,
    Satisfaction,
    SourceRecordingIdentity,
    Transcript,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=MSK)
RID = RecordingId("cdr:group-001")


def _database(tmp_path: Path) -> SqliteDatabase:
    database = SqliteDatabase(tmp_path / "calls.sqlite3")
    database.migrate()
    return database


def _recording() -> CallRecording:
    return CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(seconds=91),
        channel_layout=ChannelLayout.MONO,
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=CallerIdentity(id="79001234567"),
        operator=OperatorIdentity(id=14, extension="11198", name="Оператор"),
        source_recording=SourceRecordingIdentity(
            acct_id="901",
            filenames=("2026-08/call.wav",),
        ),
    )


def _document(recording: CallRecording) -> FinalReportDocument:
    report = CallReport(
        recording_id=recording.id,
        satisfaction=Satisfaction.SATISFIED,
        summary="Вопрос решён.",
        key_points=(),
        generated_at=NOW,
        caller_name="Анна",
        caller_name_confidence=0.92,
        question_resolved=QuestionResolution(value="yes", confidence=0.9),
    )
    return FinalReportDocument(
        recording=recording,
        report=report,
        transcript=Transcript(
            recording_id=recording.id,
            language="ru",
            segments=(),
            full_text="Анна уточнила статус заявления.",
        ),
        diarized=DiarizedTranscript(recording_id=recording.id, segments=()),
        emotions=EmotionAnalysis(recording_id=recording.id, segments=()),
    )


def _completed_job(recording: CallRecording) -> CallProcessingJob:
    job = CallProcessingJob.create(recording.id.value, recording.id, NOW)
    for stage in STAGE_ORDER:
        job = job.start_stage(stage).complete_stage(stage)
    return job


async def test_finalize_saves_report_and_done_status_atomically(tmp_path: Path) -> None:
    database = _database(tmp_path)
    calls = SqliteCallRepository(database)
    reports = SqliteFinalReportRepository(database)
    recording = _recording()
    pending = CallProcessingJob.create(recording.id.value, recording.id, NOW)
    await calls.register(recording, pending)

    await reports.finalize(_completed_job(recording), _document(recording))

    stored_job = await calls.get(recording.id.value)
    payload = await reports.load_payload(recording.id)
    assert stored_job is not None
    assert stored_job.status is JobStatus.DONE
    assert payload is not None
    assert payload["operator"]["extension"] == "11198"
    assert payload["caller"]["name"] == "Анна"


async def test_finalize_rolls_back_report_when_status_update_fails(tmp_path: Path) -> None:
    database = _database(tmp_path)
    calls = SqliteCallRepository(database)
    reports = SqliteFinalReportRepository(database)
    recording = _recording()
    pending = CallProcessingJob.create(recording.id.value, recording.id, NOW)
    await calls.register(recording, pending)
    with database.connect() as connection:
        connection.executescript(
            """
            CREATE TRIGGER reject_done
            BEFORE UPDATE OF status ON calls
            WHEN NEW.status = 'done'
            BEGIN
                SELECT RAISE(ABORT, 'done rejected');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="done rejected"):
        await reports.finalize(_completed_job(recording), _document(recording))

    assert await reports.load_payload(recording.id) is None
    stored_job = await calls.get(recording.id.value)
    assert stored_job is not None
    assert stored_job.status is JobStatus.PENDING
