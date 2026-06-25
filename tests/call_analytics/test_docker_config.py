from __future__ import annotations

from pathlib import Path


def test_voice_compose_runs_queue_worker_service() -> None:
    compose = Path("docker-compose.voice.yml").read_text(encoding="utf-8")

    assert "\n  worker:\n" in compose
    assert "python -m call_analytics.worker_app" in compose
    assert "VOICE_RABBITMQ_URL: amqp://guest:guest@rabbitmq/" in compose
