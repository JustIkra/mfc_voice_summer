from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

from call_analytics.bootstrap import Application, build_application
from call_analytics.service import AudioBackfillResult

LOGGER = logging.getLogger(__name__)


async def wait_and_backfill(
    application: Application | None = None,
    limit: int = 10000,
    poll_seconds: float = 60,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AudioBackfillResult:
    app = application or build_application()
    while True:
        processing = await app.dashboard.processing_counts()
        status = await app.dashboard.sync_status()
        pending = int(processing.get("pending", 0))
        running = int(processing.get("running", 0))
        sync_running = status is not None and status.status == "running"
        if pending == 0 and running == 0 and not sync_running:
            return await app.sync.backfill_audio(limit)
        LOGGER.info(
            "final audio backfill waits pending=%s running=%s sync_running=%s",
            pending,
            running,
            sync_running,
        )
        await sleep(poll_seconds)


async def run_service(application: Application | None = None) -> None:
    limit = _positive_int("VOICE_BACKFILL_LIMIT", 10000)
    poll_seconds = _positive_float("VOICE_BACKFILL_POLL_SECONDS", 60)
    result = await wait_and_backfill(
        application=application,
        limit=limit,
        poll_seconds=poll_seconds,
    )
    LOGGER.info(
        "final audio backfill found=%s archived=%s skipped=%s failed=%s",
        result.found,
        result.archived,
        result.skipped,
        result.failed,
    )
    await asyncio.Event().wait()


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def main() -> None:
    logging.basicConfig(level=os.getenv("VOICE_LOG_LEVEL", "INFO"))
    asyncio.run(run_service())


if __name__ == "__main__":
    main()


__all__ = ["main", "run_service", "wait_and_backfill"]
