from __future__ import annotations

import logging
import os


def get_logger() -> logging.Logger:
    logging.basicConfig(
        level=os.getenv("VOICE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger("mfc_voice_pipeline")


__all__ = ["get_logger"]
