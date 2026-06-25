from __future__ import annotations

import logging
import os

LOGGER_NAME = "mfc_voice_model_api"


def get_logger() -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    return logger
