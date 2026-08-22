from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

from call_analytics.bootstrap import MSK, build_application

LOGGER = logging.getLogger(__name__)


async def run_worker() -> None:
    logging.basicConfig(level=os.getenv("VOICE_LOG_LEVEL", "INFO"))
    idle_sleep = float(os.getenv("VOICE_WORKER_IDLE_SLEEP_SECONDS", "1"))
    app = build_application()
    recovered = await app.worker.recover_interrupted_jobs()
    cleared = await app.recording_workspace.clear_stale(datetime.now(MSK) - timedelta(hours=24))
    if recovered:
        LOGGER.warning("recovered %s interrupted jobs", recovered)
    if cleared:
        LOGGER.warning("cleared %s stale recording workspaces", cleared)
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
