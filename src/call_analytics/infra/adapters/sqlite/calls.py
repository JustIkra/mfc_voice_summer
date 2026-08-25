from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from call_analytics.infra.adapters.sqlite.database import SqliteDatabase
from call_analytics.service.ports import CallRepository, JobRepository
from domain import (
    STAGE_ORDER,
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

MSK = timezone(timedelta(hours=3))
_RETRYABLE_ERROR_KINDS = frozenset({"CONNECTION", "TIMEOUT", "RATE_LIMIT", "SERVER"})


class SqliteCallRepository(CallRepository, JobRepository):
    def __init__(
        self,
        database: SqliteDatabase,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._database = database
        self._clock = clock or (lambda: datetime.now(MSK))

    async def contains(self, recording_id: RecordingId) -> bool:
        return await asyncio.to_thread(self._contains, recording_id)

    async def register(self, recording: CallRecording, job: CallProcessingJob) -> bool:
        return await asyncio.to_thread(self._register, recording, job)

    async def register_skipped(
        self,
        call: DiscoveredCall,
        reason: str,
        now: datetime,
    ) -> None:
        await asyncio.to_thread(
            self._register_discovery,
            call,
            JobStatus.SKIPPED_EMPTY,
            "EMPTY_RECORDING",
            reason,
            now,
        )

    async def register_failed(
        self,
        call: DiscoveredCall,
        kind: str,
        reason: str,
        now: datetime,
    ) -> None:
        await asyncio.to_thread(
            self._register_discovery,
            call,
            JobStatus.FAILED,
            kind,
            reason,
            now,
        )

    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None:
        return await asyncio.to_thread(self._load_recording, recording_id)

    async def status(self, recording_id: RecordingId) -> JobStatus | None:
        return await asyncio.to_thread(self._status, recording_id)

    async def mark_skipped_empty(self, recording_id: RecordingId, reason: str) -> None:
        await asyncio.to_thread(self._mark_skipped_empty, recording_id, reason)

    async def list_retryable(self, max_attempts: int) -> Sequence[CallRecording]:
        return await asyncio.to_thread(self._list_retryable, max_attempts)

    async def save(self, job: CallProcessingJob) -> None:
        await asyncio.to_thread(self._save, job)

    async def get(self, job_id: str) -> CallProcessingJob | None:
        return await asyncio.to_thread(self._get, job_id)

    async def delete(self, job_id: str) -> None:
        await asyncio.to_thread(self._delete, job_id)

    async def list_by_status(self, status: JobStatus) -> Sequence[CallProcessingJob]:
        return await asyncio.to_thread(self._list_by_status, status)

    async def list_stale_running(self, older_than: datetime) -> Sequence[CallProcessingJob]:
        return await asyncio.to_thread(self._list_stale_running, older_than)

    def _contains(self, recording_id: RecordingId) -> bool:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM calls WHERE call_id = ?",
                (recording_id.value,),
            ).fetchone()
        return row is not None

    def _register(self, recording: CallRecording, job: CallProcessingJob) -> bool:
        queue = recording.queue or QueueIdentity(extension="", name="")
        caller = recording.caller
        operator = recording.operator
        source = recording.source_recording or SourceRecordingIdentity(acct_id=None)
        values = (
            recording.id.value,
            source.acct_id,
            _json(list(source.filenames)),
            queue.extension,
            queue.name,
            recording.started_at.isoformat(),
            recording.duration.total_seconds(),
            recording.channel_layout.name,
            caller.id,
            caller.name,
            caller.name_source.value,
            caller.name_confidence,
            operator.id if operator else None,
            operator.extension if operator else None,
            operator.name if operator else None,
            job.status.value,
            sum(job.attempts.values()),
            _json(_completed_stages(job)),
            _json(_attempts(job)),
            job.last_error[0] if job.last_error else None,
            job.last_error[1] if job.last_error else None,
            job.created_at.isoformat(),
            job.created_at.isoformat(),
        )
        try:
            with self._database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO calls (
                        call_id, recording_acct_id, recording_filenames_json,
                        queue_extension, queue_name, started_at, duration_seconds,
                        channel_layout, caller_id, caller_name, caller_name_source,
                        caller_name_confidence, operator_id, operator_extension,
                        operator_name, status, attempt_count, completed_stages_json,
                        attempts_json, last_error_kind, last_error_message,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                connection.commit()
        except sqlite3.IntegrityError:
            return False
        return True

    def _register_discovery(
        self,
        call: DiscoveredCall,
        status: JobStatus,
        error_kind: str,
        reason: str,
        now: datetime,
    ) -> None:
        source = call.source_recording
        operator = call.operator
        try:
            with self._database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO calls (
                        call_id, recording_acct_id, recording_filenames_json,
                        queue_extension, queue_name, started_at, duration_seconds,
                        channel_layout, caller_id, caller_name, caller_name_source,
                        caller_name_confidence, operator_id, operator_extension,
                        operator_name, status, attempt_count, completed_stages_json,
                        attempts_json, last_error_kind, last_error_message,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?,
                        0, '[]', '{}', ?, ?, ?, ?
                    )
                    """,
                    (
                        call.id.value,
                        source.acct_id,
                        _json(list(source.filenames)),
                        call.queue.extension,
                        call.queue.name,
                        call.started_at.isoformat(),
                        call.duration.total_seconds(),
                        call.caller.id,
                        call.caller.name,
                        call.caller.name_source.value,
                        call.caller.name_confidence,
                        operator.id if operator else None,
                        operator.extension if operator else None,
                        operator.name if operator else None,
                        status.value,
                        error_kind,
                        reason,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError:
            return

    def _load_recording(self, recording_id: RecordingId) -> CallRecording | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM calls WHERE call_id = ?",
                (recording_id.value,),
            ).fetchone()
        return _recording_from_row(row) if row is not None else None

    def _status(self, recording_id: RecordingId) -> JobStatus | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM calls WHERE call_id = ?",
                (recording_id.value,),
            ).fetchone()
        return JobStatus(str(row["status"])) if row is not None else None

    def _mark_skipped_empty(self, recording_id: RecordingId, reason: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE calls
                SET status = 'skipped_empty',
                    last_error_kind = 'EMPTY_RECORDING',
                    last_error_message = ?,
                    updated_at = ?
                WHERE call_id = ?
                """,
                (reason, self._clock().isoformat(), recording_id.value),
            )

    def _list_retryable(self, max_attempts: int) -> list[CallRecording]:
        placeholders = ",".join("?" for _ in _RETRYABLE_ERROR_KINDS)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM calls
                WHERE status = ?
                  AND attempt_count < ?
                  AND channel_layout IS NOT NULL
                  AND last_error_kind IN ({placeholders})
                ORDER BY started_at, call_id
                """,
                (JobStatus.FAILED.value, max_attempts, *_RETRYABLE_ERROR_KINDS),
            ).fetchall()
        return [recording for row in rows if (recording := _recording_from_row(row))]

    def _save(self, job: CallProcessingJob) -> None:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE calls
                SET status = ?, attempt_count = ?, completed_stages_json = ?,
                    attempts_json = ?, last_error_kind = ?, last_error_message = ?,
                    updated_at = ?
                WHERE call_id = ?
                """,
                (
                    job.status.value,
                    sum(job.attempts.values()),
                    _json(_completed_stages(job)),
                    _json(_attempts(job)),
                    job.last_error[0] if job.last_error else None,
                    job.last_error[1] if job.last_error else None,
                    self._clock().isoformat(),
                    job.id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"job {job.id} not found")

    def _get(self, job_id: str) -> CallProcessingJob | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM calls WHERE call_id = ?",
                (job_id,),
            ).fetchone()
        return _job_from_row(row) if row is not None else None

    def _delete(self, job_id: str) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM calls WHERE call_id = ?", (job_id,))

    def _list_by_status(self, status: JobStatus) -> list[CallProcessingJob]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM calls WHERE status = ? ORDER BY created_at, call_id",
                (status.value,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def _list_stale_running(self, older_than: datetime) -> list[CallProcessingJob]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM calls
                WHERE status = ? AND updated_at < ?
                ORDER BY updated_at, call_id
                """,
                (JobStatus.RUNNING.value, older_than.isoformat()),
            ).fetchall()
        return [_job_from_row(row) for row in rows]


def _recording_from_row(row: sqlite3.Row) -> CallRecording | None:
    if row["channel_layout"] is None:
        return None
    operator = None
    if row["operator_id"] is not None:
        operator = OperatorIdentity(
            id=int(row["operator_id"]),
            extension=str(row["operator_extension"]),
            name=str(row["operator_name"]),
        )
    return CallRecording(
        id=RecordingId(str(row["call_id"])),
        started_at=datetime.fromisoformat(str(row["started_at"])),
        duration=timedelta(seconds=float(row["duration_seconds"])),
        channel_layout=ChannelLayout[str(row["channel_layout"])],
        queue=QueueIdentity(
            extension=str(row["queue_extension"]),
            name=str(row["queue_name"]),
        ),
        caller=CallerIdentity(
            id=str(row["caller_id"]) if row["caller_id"] is not None else None,
            name=str(row["caller_name"]) if row["caller_name"] is not None else None,
            name_source=CallerNameSource(str(row["caller_name_source"])),
            name_confidence=float(row["caller_name_confidence"]),
        ),
        operator=operator,
        source_recording=SourceRecordingIdentity(
            acct_id=(
                str(row["recording_acct_id"]) if row["recording_acct_id"] is not None else None
            ),
            filenames=tuple(str(item) for item in json.loads(row["recording_filenames_json"])),
        ),
    )


def _job_from_row(row: sqlite3.Row) -> CallProcessingJob:
    attempts_payload = dict(json.loads(row["attempts_json"]))
    last_error = None
    if row["last_error_kind"] is not None:
        last_error = (str(row["last_error_kind"]), str(row["last_error_message"] or ""))
    return CallProcessingJob(
        id=str(row["call_id"]),
        recording_id=RecordingId(str(row["call_id"])),
        status=JobStatus(str(row["status"])),
        completed_stages=frozenset(
            JobStage(str(stage)) for stage in json.loads(row["completed_stages_json"])
        ),
        attempts={JobStage(str(stage)): int(count) for stage, count in attempts_payload.items()},
        last_error=last_error,
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )


def _completed_stages(job: CallProcessingJob) -> list[str]:
    return [stage.value for stage in STAGE_ORDER if stage in job.completed_stages]


def _attempts(job: CallProcessingJob) -> dict[str, int]:
    return {stage.value: job.attempts[stage] for stage in STAGE_ORDER if stage in job.attempts}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = ["SqliteCallRepository"]
