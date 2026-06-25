from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "docker" / "voice-model-api"


def test_voice_model_api_uses_dedicated_logger_unit() -> None:
    logger_unit = API_DIR / "logging_config.py"
    assert logger_unit.is_file()

    spec = importlib.util.spec_from_file_location("voice_model_logging_config", logger_unit)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    logger = module.get_logger()

    assert isinstance(logger, logging.Logger)
    assert logger.name == "mfc_voice_model_api"


def test_voice_model_api_does_not_use_print_logging() -> None:
    app_source = (API_DIR / "app.py").read_text(encoding="utf-8")

    assert "print(" not in app_source


def test_api_pipeline_uses_dedicated_logger_unit() -> None:
    logger_unit = ROOT / "src" / "call_analytics" / "logging_config.py"
    assert logger_unit.is_file()

    spec = importlib.util.spec_from_file_location("call_analytics_logging_config", logger_unit)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    logger = module.get_logger()

    assert isinstance(logger, logging.Logger)
    assert logger.name == "mfc_voice_pipeline"


def test_api_pipeline_does_not_use_print_logging() -> None:
    sources = [
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "call_analytics").rglob("*.py")
    ]

    assert all("print(" not in source for source in sources)
