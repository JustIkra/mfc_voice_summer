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


def test_qwen_healthcheck_uses_python3_available_in_vllm_image() -> None:
    compose = yaml.safe_load(Path("docker-compose.voice.yml").read_text(encoding="utf-8"))

    healthcheck = compose["services"]["qwen-api"]["healthcheck"]["test"]

    assert healthcheck[:2] == ["CMD", "python3"]


def test_qwen_default_context_covers_long_call_reports() -> None:
    compose = yaml.safe_load(Path("docker-compose.voice.yml").read_text(encoding="utf-8"))
    command = compose["services"]["qwen-api"]["command"]

    max_model_len_index = command.index("--max-model-len") + 1

    assert command[max_model_len_index] == "${VOICE_QWEN_MAX_MODEL_LEN:-131072}"


def test_upload_mount_is_writable_only_in_web() -> None:
    compose = yaml.safe_load(Path("docker-compose.voice.yml").read_text(encoding="utf-8"))
    web_volumes = compose["services"]["web"]["volumes"]
    worker_volumes = compose["services"]["worker"]["volumes"]

    assert "${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/uploads" in web_volumes
    assert "${VOICE_UPLOADS_HOST_DIR:-./.uploads}:/data/uploads:ro" in worker_volumes
    assert compose["services"]["web"]["environment"]["VOICE_UPLOADS_DIR"] == "/data/uploads"


def test_prod_recording_archive_remains_read_only() -> None:
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))

    for service_name in ("web", "worker"):
        assert "/media/audio:/data/recordings:ro" in compose["services"][service_name]["volumes"]
