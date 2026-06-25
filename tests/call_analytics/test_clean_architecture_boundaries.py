from __future__ import annotations

from pathlib import Path

import domain

ROOT = Path(__file__).resolve().parents[2]


def _python_files(path: str) -> list[Path]:
    return sorted((ROOT / path).rglob("*.py"))


def test_service_layer_does_not_import_infrastructure_layer() -> None:
    offenders = [
        path.relative_to(ROOT)
        for path in _python_files("src/call_analytics/service")
        if "call_analytics.infra" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_infrastructure_adapters_do_not_import_service_layer() -> None:
    offenders = [
        path.relative_to(ROOT)
        for path in _python_files("src/call_analytics/infra/adapters")
        if "from call_analytics.service import" in path.read_text(encoding="utf-8")
        or "from call_analytics.service." in path.read_text(encoding="utf-8").replace(
            "from call_analytics.service.ports", ""
        )
    ]

    assert offenders == []


def test_application_ports_do_not_define_dataclasses() -> None:
    source = (ROOT / "src/call_analytics/service/ports/application.py").read_text(
        encoding="utf-8"
    )

    assert "from dataclasses import dataclass" not in source
    assert "@dataclass" not in source
    assert getattr(domain, "Period", None) is not None


def test_model_api_adapters_do_not_import_sibling_adapter_modules() -> None:
    offenders = [
        path.relative_to(ROOT)
        for path in _python_files("src/call_analytics/infra/adapters/model_api")
        if path.name not in {"__init__.py"}
        and "call_analytics.infra.adapters.model_api." in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
