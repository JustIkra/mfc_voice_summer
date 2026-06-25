from __future__ import annotations

import asyncio
import logging
import os

from call_analytics.bootstrap import build_application

LOGGER = logging.getLogger(__name__)


async def run_worker() -> None:
    logging.basicConfig(level=os.getenv("VOICE_LOG_LEVEL", "INFO"))
    idle_sleep = float(os.getenv("VOICE_WORKER_IDLE_SLEEP_SECONDS", "1"))
    app = build_application()
    while True:
        try:
            processed = await app.worker.run_once()
        except Exception:
            LOGGER.exception("processing worker iteration failed")
            await asyncio.sleep(idle_sleep)
            continue
        if not processed:
            await asyncio.sleep(idle_sleep)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
