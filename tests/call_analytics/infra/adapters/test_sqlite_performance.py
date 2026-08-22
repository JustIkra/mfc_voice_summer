from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from call_analytics.infra.adapters.sqlite import (
    SqliteDashboardRepository,
    SqliteDatabase,
    compress_payload,
)
from call_analytics.service.dashboard import CallPageRequest, DashboardFilter

MSK = timezone(timedelta(hours=3))
STARTED_AT = datetime(2026, 8, 22, 10, 0, tzinfo=MSK)


def test_dashboard_first_page_under_target_with_100k_rows(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "calls.sqlite3")
    database.migrate()
    _seed(database, 100_000)
    repository = SqliteDashboardRepository(database)
    filters = DashboardFilter(
        date_from=STARTED_AT - timedelta(days=1),
        date_to=STARTED_AT + timedelta(days=1),
    )

    started = time.perf_counter()
    summary = asyncio.run(repository.summary(filters))
    page = asyncio.run(
        repository.list_calls(CallPageRequest(filters=filters, page=1, page_size=50))
    )
    elapsed = time.perf_counter() - started

    assert summary.total_calls == 100_000
    assert page.total_items == 100_000
    assert len(page.items) == 50
    assert elapsed < 0.5

    with database.connect() as connection:
        plan = connection.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT COUNT(*)
            FROM calls c JOIN reports r ON r.call_id = c.call_id
            WHERE c.status = 'done' AND c.started_at >= ? AND c.started_at <= ?
            """,
            (filters.date_from.isoformat(), filters.date_to.isoformat()),
        ).fetchall()
    assert any("idx_calls_status" in str(row[3]) for row in plan)


def _seed(database: SqliteDatabase, count: int) -> None:
    payload = compress_payload({"schema_version": 1, "analysis": {"summary": "ok"}})
    started_at = STARTED_AT.isoformat()
    with database.connect() as connection:
        connection.executemany(
            """
            INSERT INTO calls (
                call_id, recording_filenames_json, queue_extension, queue_name,
                started_at, duration_seconds, channel_layout, caller_id,
                operator_id, operator_extension, operator_name, status,
                created_at, updated_at
            ) VALUES (?, ?, '6500', 'Call_center', ?, 180.0, 'MONO', ?, 14, '11198',
                      'Оператор', 'done', ?, ?)
            """,
            (
                (
                    f"cdr:{index:06d}",
                    json.dumps([f"call-{index:06d}.wav"]),
                    started_at,
                    f"caller-{index:06d}",
                    started_at,
                    started_at,
                )
                for index in range(count)
            ),
        )
        connection.executemany(
            """
            INSERT INTO reports (
                call_id, schema_version, satisfaction, question_resolved,
                client_satisfaction_score, summary, attention_required,
                generated_at, payload_codec, payload_compressed
            ) VALUES (?, 1, 'satisfied', 'yes', 5, 'ok', 0, ?, 'zlib', ?)
            """,
            ((f"cdr:{index:06d}", started_at, payload) for index in range(count)),
        )
