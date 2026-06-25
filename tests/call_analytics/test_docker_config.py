from __future__ import annotations

from pathlib import Path

import yaml


def test_voice_compose_runs_queue_worker_service() -> None:
    compose = Path("docker-compose.voice.yml").read_text(encoding="utf-8")

    assert "\n  worker:\n" in compose
    assert "python -m call_analytics.worker_app" in compose
    assert "VOICE_RABBITMQ_URL: amqp://guest:guest@rabbitmq/" in compose


def test_voice_model_api_services_build_local_image() -> None:
    compose = yaml.safe_load(Path("docker-compose.voice.yml").read_text(encoding="utf-8"))

    for service_name in ("asr-api", "diarization-api", "emotion-api"):
        service = compose["services"][service_name]

        assert service["image"] == "mfc-voice-model-api:latest"
        assert service["build"]["context"] == "./docker/voice-model-api"
