from __future__ import annotations

from pathlib import Path

from call_analytics.bootstrap import AppSettings, build_application
from call_analytics.infra.adapters.local_dir import (
    LocalArtifactStore,
    LocalDirectoryRecordingSource,
    LocalJobRepository,
)
from call_analytics.infra.adapters.queue import RabbitMQProcessingQueue
from call_analytics.service import CallProcessingService, ProcessingWorker


def test_build_application_wires_pipeline_worker_and_rabbitmq_queue(tmp_path) -> None:
    settings = AppSettings(
        recordings_dir=tmp_path / "recordings",
        artifacts_dir=tmp_path / "artifacts",
        asr_url="http://asr:8100",
        diarization_url="http://diarization:8100",
        emotion_url="http://emotion:8100",
        qwen_base_url="http://qwen:8000/v1",
        qwen_model="qwen3.6-35b",
        container_recordings_dir="/data/recordings",
        rabbitmq_url="amqp://guest:guest@rabbitmq/",
    )

    app = build_application(settings)

    assert isinstance(app.pipeline, CallProcessingService)
    assert isinstance(app.worker, ProcessingWorker)
    assert app.worker.requeue_failed is False
    assert isinstance(app.source, LocalDirectoryRecordingSource)
    assert isinstance(app.jobs, LocalJobRepository)
    assert isinstance(app.artifacts, LocalArtifactStore)
    assert isinstance(app.queue, RabbitMQProcessingQueue)


def test_settings_from_env_uses_local_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VOICE_RECORDINGS_DIR", str(tmp_path / "input"))
    monkeypatch.setenv("VOICE_ARTIFACTS_DIR", str(tmp_path / "out"))

    settings = AppSettings.from_env()

    assert settings.recordings_dir == Path(tmp_path / "input")
    assert settings.artifacts_dir == Path(tmp_path / "out")
    assert settings.asr_url == "http://127.0.0.1:8101"
