from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from call_analytics.sync_app import _parser, next_run

MSK = timezone(timedelta(hours=3))


def test_next_run_uses_same_day_before_schedule() -> None:
    now = datetime(2026, 8, 22, 1, 30, tzinfo=MSK)

    assert next_run(now, time(2, 0)) == datetime(2026, 8, 22, 2, 0, tzinfo=MSK)


def test_next_run_uses_next_day_at_or_after_schedule() -> None:
    now = datetime(2026, 8, 22, 2, 0, tzinfo=MSK)

    assert next_run(now, time(2, 0)) == datetime(2026, 8, 23, 2, 0, tzinfo=MSK)


def test_parser_accepts_audio_backfill_mode() -> None:
    args = _parser().parse_args(["--backfill-audio", "--limit", "25"])

    assert args.backfill_audio is True
    assert args.once is False
    assert args.limit == 25
