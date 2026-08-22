from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from call_analytics.infra.adapters.grandstream import GrandstreamClient
from call_analytics.infra.adapters.model_api import (
    MountedDirectoryAudioStager,
    QwenReportGenerator,
    VoiceModelDiarizer,
    VoiceModelEmotionRecognizer,
    VoiceModelTranscriber,
)
from call_analytics.infra.adapters.queue import RabbitMQProcessingQueue
from call_analytics.infra.adapters.sqlite import (
    SqliteCallRepository,
    SqliteDashboardRepository,
    SqliteDatabase,
    SqliteFinalReportRepository,
    SqliteSyncRunRepository,
)
from call_analytics.infra.adapters.transient import FilesystemRecordingWorkspace
from call_analytics.service import (
    CallProcessingService,
    DashboardService,
    DialogueAssembler,
    GrandstreamSyncService,
    PipelineWorkspace,
    ProcessingWorker,
)
from call_analytics.service.ports import (
    ArtifactStore,
    CallRecordingSource,
    CallRepository,
    DashboardRepository,
    FinalReportRepository,
    JobRepository,
    ProcessingQueue,
    RecordingWorkspace,
    SyncRunRepository,
)

MSK = timezone(timedelta(hours=3))


@dataclass(frozen=True, slots=True)
class AppSettings:
    db_path: Path = Path(".data/call-analytics.sqlite3")
    staging_dir: Path = Path(".staging")
    asr_url: str = "http://127.0.0.1:8101"
    diarization_url: str = "http://127.0.0.1:8102"
    emotion_url: str = "http://127.0.0.1:8103"
    qwen_base_url: str = "http://127.0.0.1:8000/v1"
    qwen_model: str = "qwen3.6-35b"
    qwen_report_timeout_seconds: int = 600
    qwen_report_max_tokens: int = 8192
    container_staging_dir: str = "/data/staging"
    rabbitmq_url: str | None = None
    rabbitmq_queue_name: str = "voice.recordings"
    grandstream_url: str = "https://grandstream253.mfcl.mfclnr.ru/api"
    grandstream_user: str = "ranhigs"
    grandstream_password: str = ""
    grandstream_queue: str = "6500"
    grandstream_queue_name: str = "Call_center"
    grandstream_ca_file: Path = Path("docker/certs/mfcRootCA.crt")
    grandstream_api_timeout_seconds: int = 120
    grandstream_download_timeout_seconds: int = 900
    sync_time: time = time(2, 0)
    sync_batch_limit: int = 1000
    sync_enabled: bool = False
    sync_run_on_start: bool = False

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(
            db_path=Path(os.getenv("VOICE_DB_PATH", ".data/call-analytics.sqlite3")),
            staging_dir=Path(os.getenv("VOICE_STAGING_DIR", ".staging")),
            asr_url=os.getenv("VOICE_ASR_URL", "http://127.0.0.1:8101"),
            diarization_url=os.getenv("VOICE_DIARIZATION_URL", "http://127.0.0.1:8102"),
            emotion_url=os.getenv("VOICE_EMOTION_URL", "http://127.0.0.1:8103"),
            qwen_base_url=os.getenv("VOICE_QWEN_BASE_URL", "http://127.0.0.1:8000/v1"),
            qwen_model=os.getenv("VOICE_QWEN_MODEL", "qwen3.6-35b"),
            qwen_report_timeout_seconds=int(os.getenv("VOICE_QWEN_REPORT_TIMEOUT_SECONDS", "600")),
            qwen_report_max_tokens=int(os.getenv("VOICE_QWEN_REPORT_MAX_TOKENS", "8192")),
            container_staging_dir=os.getenv(
                "VOICE_CONTAINER_STAGING_DIR",
                "/data/staging",
            ),
            rabbitmq_url=os.getenv("VOICE_RABBITMQ_URL") or None,
            rabbitmq_queue_name=os.getenv("VOICE_RABBITMQ_QUEUE", "voice.recordings"),
            grandstream_url=os.getenv(
                "VOICE_GRANDSTREAM_URL",
                "https://grandstream253.mfcl.mfclnr.ru/api",
            ),
            grandstream_user=os.getenv("VOICE_GRANDSTREAM_USER", "ranhigs"),
            grandstream_password=os.getenv("VOICE_GRANDSTREAM_PASSWORD", ""),
            grandstream_queue=os.getenv("VOICE_GRANDSTREAM_QUEUE", "6500"),
            grandstream_queue_name=os.getenv(
                "VOICE_GRANDSTREAM_QUEUE_NAME",
                "Call_center",
            ),
            grandstream_ca_file=Path(
                os.getenv(
                    "VOICE_GRANDSTREAM_CA_FILE",
                    "docker/certs/mfcRootCA.crt",
                )
            ),
            grandstream_api_timeout_seconds=int(
                os.getenv("VOICE_GRANDSTREAM_API_TIMEOUT_SECONDS", "120")
            ),
            grandstream_download_timeout_seconds=int(
                os.getenv("VOICE_GRANDSTREAM_DOWNLOAD_TIMEOUT_SECONDS", "900")
            ),
            sync_time=_parse_time(os.getenv("VOICE_SYNC_TIME", "02:00")),
            sync_batch_limit=_positive_int("VOICE_SYNC_BATCH_LIMIT", 1000),
            sync_enabled=_env_bool("VOICE_SYNC_ENABLED", False),
            sync_run_on_start=_env_bool("VOICE_SYNC_RUN_ON_START", False),
        )


@dataclass(frozen=True, slots=True)
class Application:
    settings: AppSettings
    source: CallRecordingSource
    jobs: JobRepository
    artifacts: ArtifactStore
    calls: CallRepository
    final_reports: FinalReportRepository
    dashboard_repository: DashboardRepository
    sync_runs: SyncRunRepository
    recording_workspace: RecordingWorkspace
    queue: ProcessingQueue
    pipeline: CallProcessingService
    workspace: PipelineWorkspace
    worker: ProcessingWorker
    dashboard: DashboardService
    sync: GrandstreamSyncService


def build_application(settings: AppSettings | None = None) -> Application:
    settings = settings or AppSettings.from_env()
    database = SqliteDatabase(settings.db_path)
    database.migrate()
    calls = SqliteCallRepository(database)
    final_reports = SqliteFinalReportRepository(database)
    dashboard_repository = SqliteDashboardRepository(database)
    sync_runs = SqliteSyncRunRepository(database)
    recording_workspace = FilesystemRecordingWorkspace(
        settings.staging_dir,
        settings.container_staging_dir,
    )
    queue = RabbitMQProcessingQueue(
        settings.rabbitmq_url or "amqp://guest:guest@localhost/",
        queue_name=settings.rabbitmq_queue_name,
    )
    audio_stager = MountedDirectoryAudioStager(
        host_directory=settings.staging_dir,
        model_directory=settings.container_staging_dir,
    )
    pipeline = CallProcessingService(
        source=recording_workspace,
        transcriber=VoiceModelTranscriber(
            base_url=settings.asr_url,
            audio_stager=audio_stager,
        ),
        diarizer=VoiceModelDiarizer(
            base_url=settings.diarization_url,
            audio_stager=audio_stager,
        ),
        emotion_recognizer=VoiceModelEmotionRecognizer(
            base_url=settings.emotion_url,
            audio_stager=audio_stager,
        ),
        report_generator=QwenReportGenerator(
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
            clock=lambda: datetime.now(MSK),
            assembler=DialogueAssembler(),
            timeout_seconds=settings.qwen_report_timeout_seconds,
            max_tokens=settings.qwen_report_max_tokens,
        ),
        jobs=calls,
        artifacts=recording_workspace,
        calls=calls,
        final_reports=final_reports,
        workspace=recording_workspace,
        clock=lambda: datetime.now(MSK),
    )
    workspace = PipelineWorkspace(
        source=recording_workspace,
        jobs=calls,
        artifacts=recording_workspace,
        queue=queue,
        pipeline=pipeline,
        clock=lambda: datetime.now(MSK),
    )
    worker = ProcessingWorker(
        queue=queue,
        pipeline=pipeline,
        jobs=calls,
        requeue_failed=False,
        workspace=recording_workspace,
    )
    gateway = GrandstreamClient(
        base_url=settings.grandstream_url,
        username=settings.grandstream_user,
        password=settings.grandstream_password,
        queue_extension=settings.grandstream_queue,
        queue_name=settings.grandstream_queue_name,
        ca_file=settings.grandstream_ca_file,
        api_timeout_seconds=settings.grandstream_api_timeout_seconds,
        download_timeout_seconds=settings.grandstream_download_timeout_seconds,
    )
    sync = GrandstreamSyncService(
        gateway=gateway,
        workspace=recording_workspace,
        calls=calls,
        jobs=calls,
        sync_runs=sync_runs,
        queue=queue,
        queue_extension=settings.grandstream_queue,
    )
    dashboard = DashboardService(
        dashboard=dashboard_repository,
        reports=final_reports,
        sync_runs=sync_runs,
    )
    return Application(
        settings=settings,
        source=recording_workspace,
        jobs=calls,
        artifacts=recording_workspace,
        calls=calls,
        final_reports=final_reports,
        dashboard_repository=dashboard_repository,
        sync_runs=sync_runs,
        recording_workspace=recording_workspace,
        queue=queue,
        pipeline=pipeline,
        workspace=workspace,
        worker=worker,
        dashboard=dashboard,
        sync=sync,
    )


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"VOICE_SYNC_TIME must be HH:MM, got {value!r}") from error


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be yes/no, got {value!r}")


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive, got {value!r}")
    return value


__all__ = ["MSK", "AppSettings", "Application", "build_application"]
