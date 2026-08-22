from __future__ import annotations

import asyncio
import json
from typing import cast

from call_analytics.infra.adapters.sqlite.database import SqliteDatabase
from call_analytics.infra.adapters.sqlite.serialization import (
    compress_payload,
    decompress_payload,
)
from call_analytics.service.ports import FinalReportRepository
from domain import (
    STAGE_ORDER,
    CallProcessingJob,
    FinalReportDocument,
    RecordingId,
    Satisfaction,
    build_report_payload,
)


class SqliteFinalReportRepository(FinalReportRepository):
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def finalize(self, job: CallProcessingJob, document: FinalReportDocument) -> None:
        await asyncio.to_thread(self._finalize, job, document)

    async def load_payload(self, recording_id: RecordingId) -> dict[str, object] | None:
        return await asyncio.to_thread(self._load_payload, recording_id)

    def _finalize(self, job: CallProcessingJob, document: FinalReportDocument) -> None:
        recording_id = document.recording.id
        if {
            job.recording_id,
            document.report.recording_id,
            document.transcript.recording_id,
            document.diarized.recording_id,
            document.emotions.recording_id,
        } != {recording_id}:
            raise ValueError("final report inputs have different recording ids")
        payload = build_report_payload(document)
        report = document.report
        caller = cast(dict[str, object], payload["caller"])
        caller_name = caller.get("name")
        caller_source = caller.get("name_source")
        caller_confidence = float(cast(float | int | str, caller.get("name_confidence", 0.0)))
        attention_required = int(
            report.satisfaction is Satisfaction.DISSATISFIED or bool(report.risks)
        )
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO reports (
                    call_id, schema_version, satisfaction, question_resolved,
                    client_satisfaction_score, summary, attention_required,
                    generated_at, payload_codec, payload_compressed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'zlib', ?)
                ON CONFLICT(call_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    satisfaction = excluded.satisfaction,
                    question_resolved = excluded.question_resolved,
                    client_satisfaction_score = excluded.client_satisfaction_score,
                    summary = excluded.summary,
                    attention_required = excluded.attention_required,
                    generated_at = excluded.generated_at,
                    payload_codec = excluded.payload_codec,
                    payload_compressed = excluded.payload_compressed
                """,
                (
                    recording_id.value,
                    int(cast(int, payload["schema_version"])),
                    report.satisfaction.name.lower(),
                    report.question_resolved.value,
                    report.client_satisfaction.score_1_5,
                    report.summary,
                    attention_required,
                    report.generated_at.isoformat(),
                    compress_payload(payload),
                ),
            )
            cursor = connection.execute(
                """
                UPDATE calls
                SET status = ?, attempt_count = ?, completed_stages_json = ?,
                    attempts_json = ?, last_error_kind = NULL,
                    last_error_message = NULL,
                    caller_name = CASE
                        WHEN ? IS NOT NULL AND ? > caller_name_confidence THEN ?
                        ELSE caller_name
                    END,
                    caller_name_source = CASE
                        WHEN ? IS NOT NULL AND ? > caller_name_confidence THEN ?
                        ELSE caller_name_source
                    END,
                    caller_name_confidence = CASE
                        WHEN ? IS NOT NULL AND ? > caller_name_confidence THEN ?
                        ELSE caller_name_confidence
                    END,
                    updated_at = ?
                WHERE call_id = ?
                """,
                (
                    job.status.value,
                    sum(job.attempts.values()),
                    _json([stage.value for stage in STAGE_ORDER if stage in job.completed_stages]),
                    _json(
                        {
                            stage.value: job.attempts[stage]
                            for stage in STAGE_ORDER
                            if stage in job.attempts
                        }
                    ),
                    caller_name,
                    caller_confidence,
                    caller_name,
                    caller_name,
                    caller_confidence,
                    caller_source,
                    caller_name,
                    caller_confidence,
                    caller_confidence,
                    report.generated_at.isoformat(),
                    recording_id.value,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"call {recording_id.value} not found")
            connection.commit()

    def _load_payload(self, recording_id: RecordingId) -> dict[str, object] | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_codec, payload_compressed FROM reports WHERE call_id = ?",
                (recording_id.value,),
            ).fetchone()
        if row is None:
            return None
        codec = str(row["payload_codec"])
        if codec != "zlib":
            raise ValueError(f"unsupported report payload codec {codec}")
        return decompress_payload(bytes(row["payload_compressed"]))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = ["SqliteFinalReportRepository"]
