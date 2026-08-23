from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.sqlite import (
    SqliteDashboardRepository,
    SqliteDatabase,
    compress_payload,
)
from call_analytics.service.dashboard import CallPageRequest, DashboardFilter

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
DATE_FROM = datetime(2026, 8, 1, tzinfo=MSK)
DATE_TO = datetime(2026, 8, 31, 23, 59, 59, tzinfo=MSK)


def _repository(tmp_path: Path) -> SqliteDashboardRepository:
    database = SqliteDatabase(tmp_path / "calls.sqlite3")
    database.migrate()
    with database.connect() as connection:
        _insert_call(
            connection,
            call_id="cdr:1",
            started_at=datetime(2026, 8, 20, 10, 0, tzinfo=MSK),
            duration=120.0,
            status="done",
            operator_id=14,
            operator_extension="11198",
            operator_name="Первый оператор",
            caller_id="abc%def",
            satisfaction="satisfied",
            resolved="yes",
            summary="Статус заявления",
            attention=0,
        )
        _insert_call(
            connection,
            call_id="cdr:2",
            started_at=datetime(2026, 8, 21, 10, 0, tzinfo=MSK),
            duration=240.0,
            status="done",
            operator_id=15,
            operator_extension="11195",
            operator_name="Второй оператор",
            caller_id="79000000002",
            satisfaction="dissatisfied",
            resolved="no",
            summary="Жалоба на срок",
            attention=1,
        )
        _insert_call(
            connection,
            call_id="cdr:failed",
            started_at=datetime(2026, 8, 22, 10, 0, tzinfo=MSK),
            duration=300.0,
            status="failed",
            operator_id=14,
            operator_extension="11198",
            operator_name="Первый оператор",
            caller_id="79000000003",
        )
    return SqliteDashboardRepository(database)


def _insert_call(
    connection,
    *,
    call_id: str,
    started_at: datetime,
    duration: float,
    status: str,
    operator_id: int,
    operator_extension: str,
    operator_name: str,
    caller_id: str,
    satisfaction: str | None = None,
    resolved: str | None = None,
    summary: str = "",
    attention: int = 0,
) -> None:
    connection.execute(
        """
        INSERT INTO calls (
            call_id, recording_filenames_json, queue_extension, queue_name,
            started_at, duration_seconds, channel_layout, caller_id,
            operator_id, operator_extension, operator_name, status,
            created_at, updated_at
        ) VALUES (?, '["call.wav"]', '6500', 'Call_center', ?, ?, 'MONO', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            call_id,
            started_at.isoformat(),
            duration,
            caller_id,
            operator_id,
            operator_extension,
            operator_name,
            status,
            started_at.isoformat(),
            started_at.isoformat(),
        ),
    )
    if status == "done":
        payload = {
            "schema_version": 1,
            "call": {"id": call_id},
            "analysis": {"summary": summary},
        }
        connection.execute(
            """
            INSERT INTO reports (
                call_id, schema_version, satisfaction, question_resolved,
                client_satisfaction_score, summary, attention_required,
                generated_at, payload_codec, payload_compressed
            ) VALUES (?, 1, ?, ?, 3, ?, ?, ?, 'zlib', ?)
            """,
            (
                call_id,
                satisfaction,
                resolved,
                summary,
                attention,
                started_at.isoformat(),
                compress_payload(payload),
            ),
        )


async def test_summary_and_operator_rows_exclude_failed_calls(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    filters = DashboardFilter(DATE_FROM, DATE_TO)

    summary = await repository.summary(filters)
    operators = await repository.operators(filters)

    assert summary.total_calls == 2
    assert summary.resolved_calls == 1
    assert summary.average_duration_seconds == 180.0
    assert summary.attention_calls == 1
    assert summary.satisfaction == {"satisfied": 1, "neutral": 0, "dissatisfied": 1}
    assert [(item.id, item.total_calls) for item in operators] == [(14, 1), (15, 1)]


async def test_processing_counts_include_non_report_jobs(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    counts = await repository.processing_counts()

    assert counts == {
        "pending": 0,
        "running": 0,
        "done": 2,
        "failed": 1,
        "skipped_empty": 0,
    }


async def test_list_calls_filters_pages_and_escapes_wildcards(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    request = CallPageRequest(
        filters=DashboardFilter(DATE_FROM, DATE_TO, query="%"),
        page=1,
        page_size=1,
    )

    page = await repository.list_calls(request)

    assert page.total_items == 1
    assert page.page_size == 1
    assert [item.call_id for item in page.items] == ["cdr:1"]
    assert page.items[0].recording_filenames == ("call.wav",)
