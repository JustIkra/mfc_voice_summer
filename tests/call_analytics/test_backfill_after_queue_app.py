from __future__ import annotations

from types import SimpleNamespace

import pytest

from call_analytics.backfill_after_queue_app import wait_and_backfill
from call_analytics.service import AudioBackfillResult

pytestmark = pytest.mark.asyncio


class FakeDashboard:
    def __init__(self) -> None:
        self.counts = [
            {"pending": 2, "running": 1},
            {"pending": 0, "running": 0},
            {"pending": 0, "running": 0},
        ]
        self.sync_statuses = [
            SimpleNamespace(status="done"),
            SimpleNamespace(status="running"),
            SimpleNamespace(status="done"),
        ]

    async def processing_counts(self):
        return self.counts.pop(0)

    async def sync_status(self):
        return self.sync_statuses.pop(0)


class FakeSync:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def backfill_audio(self, limit: int) -> AudioBackfillResult:
        self.limits.append(limit)
        return AudioBackfillResult(found=10, archived=10, skipped=20, failed=0)


async def test_waits_for_empty_queue_and_idle_sync_before_backfill() -> None:
    dashboard = FakeDashboard()
    sync = FakeSync()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    application = SimpleNamespace(dashboard=dashboard, sync=sync)

    result = await wait_and_backfill(
        application=application,
        limit=10000,
        poll_seconds=60,
        sleep=fake_sleep,
    )

    assert result == AudioBackfillResult(found=10, archived=10, skipped=20, failed=0)
    assert sync.limits == [10000]
    assert sleeps == [60, 60]
