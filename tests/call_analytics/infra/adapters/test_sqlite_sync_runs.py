from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.sqlite import SqliteDatabase, SqliteSyncRunRepository
from domain import Period

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 22, 2, 0, tzinfo=MSK)
PERIOD = Period(start=NOW - timedelta(days=30), end=NOW)


async def test_only_one_running_sync_and_last_status_round_trip(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "calls.sqlite3")
    database.migrate()
    repository = SqliteSyncRunRepository(database)

    run_id = await repository.start(PERIOD, NOW)
    concurrent = await repository.start(PERIOD, NOW)

    assert run_id is not None
    assert concurrent is None

    await repository.finish(
        run_id,
        finished_at=NOW + timedelta(minutes=2),
        status="done",
        discovered=3,
        queued=2,
        skipped=1,
        failed=0,
    )
    last = await repository.last()

    assert last is not None
    assert last.status == "done"
    assert last.window_start == PERIOD.start
    assert last.window_end == PERIOD.end
    assert last.discovered == 3
    assert last.queued == 2
    assert last.skipped == 1
    assert last.error_kind is None
    assert last.error_message is None
    assert await repository.start(PERIOD, NOW + timedelta(days=1)) is not None
