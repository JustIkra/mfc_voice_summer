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


def test_runtime_uses_sqlite_and_transient_staging_without_archive_mounts() -> None:
    compose = yaml.safe_load(Path("docker-compose.voice.yml").read_text(encoding="utf-8"))
    web_volumes = compose["services"]["web"]["volumes"]
    worker_volumes = compose["services"]["worker"]["volumes"]
    sync_volumes = compose["services"]["grandstream-sync"]["volumes"]

    assert "./.data:/data/db" in web_volumes
    assert "./.data:/data/db" in worker_volumes
    assert "./.data:/data/db" in sync_volumes
    assert "./.staging:/data/staging" in worker_volumes
    assert "./.staging:/data/staging" in sync_volumes
    serialized = Path("docker-compose.voice.yml").read_text(encoding="utf-8")
    assert "/media/audio" not in serialized
    assert "VOICE_UPLOADS_DIR" not in serialized
    assert ".reports" not in serialized


def test_compose_adds_disabled_by_default_grandstream_sync() -> None:
    compose = yaml.safe_load(Path("docker-compose.voice.yml").read_text(encoding="utf-8"))
    service = compose["services"]["grandstream-sync"]

    assert service["command"] == "python -m call_analytics.sync_app"
    assert service["environment"]["VOICE_DB_PATH"] == "/data/db/call-analytics.sqlite3"
    assert service["environment"]["VOICE_SYNC_ENABLED"] == "${VOICE_SYNC_ENABLED:-no}"
    assert service["environment"]["VOICE_GRANDSTREAM_QUEUE"] == "${VOICE_GRANDSTREAM_QUEUE:-6500}"


def test_prod_override_does_not_restore_archive_or_upload_mounts() -> None:
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    serialized = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "/media/audio" not in serialized
    assert "uploads" not in serialized
    assert compose["services"]["qwen-api"]["deploy"]["resources"]["reservations"]


def test_web_image_installs_ffmpeg_and_internal_ca() -> None:
    dockerfile = Path("docker/web/Dockerfile").read_text(encoding="utf-8")

    assert "ffmpeg" in dockerfile
    assert "ca-certificates" in dockerfile
    assert "mfcRootCA.crt" in dockerfile
    assert "update-ca-certificates" in dockerfile
