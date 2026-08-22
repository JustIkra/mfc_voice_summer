from __future__ import annotations

from datetime import time
from pathlib import Path

from call_analytics.bootstrap import AppSettings, build_application
from call_analytics.infra.adapters.queue import RabbitMQProcessingQueue
from call_analytics.infra.adapters.sqlite import (
    SqliteCallRepository,
    SqliteDashboardRepository,
    SqliteFinalReportRepository,
    SqliteSyncRunRepository,
)
from call_analytics.infra.adapters.transient import FilesystemRecordingWorkspace
from call_analytics.service import (
    CallProcessingService,
    DashboardService,
    GrandstreamSyncService,
    ProcessingWorker,
)


def test_build_application_wires_sqlite_workspace_worker_and_sync(tmp_path: Path) -> None:
    settings = AppSettings(
        db_path=tmp_path / "data" / "calls.sqlite3",
        staging_dir=tmp_path / "staging",
        asr_url="http://asr:8100",
        diarization_url="http://diarization:8100",
        emotion_url="http://emotion:8100",
        qwen_base_url="http://qwen:8000/v1",
        qwen_model="qwen3.6-35b",
        container_staging_dir="/data/staging",
        rabbitmq_url="amqp://guest:guest@rabbitmq/",
        grandstream_url="https://ucm.example/api",
        grandstream_user="api-user",
        grandstream_password="secret",
        grandstream_queue="6500",
        grandstream_queue_name="Call_center",
        grandstream_ca_file=tmp_path / "ca.crt",
    )

    app = build_application(settings)

    assert isinstance(app.pipeline, CallProcessingService)
    assert isinstance(app.worker, ProcessingWorker)
    assert isinstance(app.sync, GrandstreamSyncService)
    assert isinstance(app.dashboard, DashboardService)
    assert isinstance(app.source, FilesystemRecordingWorkspace)
    assert isinstance(app.artifacts, FilesystemRecordingWorkspace)
    assert isinstance(app.jobs, SqliteCallRepository)
    assert isinstance(app.calls, SqliteCallRepository)
    assert isinstance(app.final_reports, SqliteFinalReportRepository)
    assert isinstance(app.dashboard_repository, SqliteDashboardRepository)
    assert isinstance(app.sync_runs, SqliteSyncRunRepository)
    assert isinstance(app.queue, RabbitMQProcessingQueue)
    assert settings.db_path.is_file()


def test_settings_from_env_reads_grandstream_and_sqlite(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOICE_DB_PATH", str(tmp_path / "calls.sqlite3"))
    monkeypatch.setenv("VOICE_STAGING_DIR", str(tmp_path / "stage"))
    monkeypatch.setenv("VOICE_GRANDSTREAM_URL", "https://ucm.example/api")
    monkeypatch.setenv("VOICE_GRANDSTREAM_USER", "api-user")
    monkeypatch.setenv("VOICE_GRANDSTREAM_PASSWORD", "secret")
    monkeypatch.setenv("VOICE_GRANDSTREAM_QUEUE", "6500")
    monkeypatch.setenv("VOICE_SYNC_TIME", "02:00")
    monkeypatch.setenv("VOICE_SYNC_ENABLED", "yes")

    settings = AppSettings.from_env()

    assert settings.db_path == tmp_path / "calls.sqlite3"
    assert settings.staging_dir == tmp_path / "stage"
    assert settings.grandstream_url == "https://ucm.example/api"
    assert settings.grandstream_user == "api-user"
    assert settings.grandstream_password == "secret"
    assert settings.grandstream_queue == "6500"
    assert settings.sync_time == time(2, 0)
    assert settings.sync_enabled is True
