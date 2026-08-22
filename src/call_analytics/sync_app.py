from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, time, timedelta

from call_analytics.bootstrap import MSK, Application, build_application

LOGGER = logging.getLogger(__name__)


def next_run(now: datetime, scheduled: time) -> datetime:
    candidate = datetime.combine(now.date(), scheduled, tzinfo=now.tzinfo)
    return candidate if candidate > now else candidate + timedelta(days=1)


async def run_once(limit: int | None = None, application: Application | None = None) -> None:
    app = application or build_application()
    await app.sync.run_once(datetime.now(MSK), limit=limit)


async def run_scheduler(
    application: Application | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(MSK),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    app = application or build_application()
    if not app.settings.sync_enabled:
        LOGGER.info("Grandstream scheduler is disabled")
        await asyncio.Event().wait()
    if app.settings.sync_run_on_start:
        await app.sync.run_once(clock())
    while True:
        now = clock()
        await sleep((next_run(now, app.settings.sync_time) - now).total_seconds())
        await app.sync.run_once(clock())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grandstream-sync")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=os.getenv("VOICE_LOG_LEVEL", "INFO"))
    args = _parser().parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.once:
        asyncio.run(run_once(limit=args.limit))
    else:
        asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()


__all__ = ["main", "next_run", "run_once", "run_scheduler"]
