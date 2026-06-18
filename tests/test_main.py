from datetime import datetime, timedelta, timezone

import pytest

from domain import CallReport, Satisfaction
from main import run_demo

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))


async def test_run_demo_produces_report() -> None:
    report = await run_demo(clock=lambda: datetime(2026, 1, 10, 12, 0, tzinfo=MSK))
    assert isinstance(report, CallReport)
    assert report.recording_id.value == "demo-1"
    assert report.satisfaction is Satisfaction.NEUTRAL
    assert report.summary
