from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from call_analytics.infra.adapters.local_dir import (
    LocalArtifactStore,
    LocalDirectoryRecordingInbox,
    LocalDirectoryRecordingSource,
    LocalJobRepository,
)
from call_analytics.infra.adapters.model_api import (
    MountedDirectoryAudioStager,
    QwenReportGenerator,
    VoiceModelDiarizer,
    VoiceModelEmotionRecognizer,
    VoiceModelTranscriber,
)
from call_analytics.infra.adapters.queue import RabbitMQProcessingQueue
from call_analytics.infra.adapters.reporting import ReportLabReportRenderer
from call_analytics.service import (
    CallProcessingService,
    DialogueAssembler,
    PipelineWorkspace,
    ProcessingWorker,
)
from call_analytics.service.ports import (
    ArtifactStore,
    CallRecordingSource,
    JobRepository,
    ProcessingQueue,
)

MSK = timezone(timedelta(hours=3))


@dataclass(frozen=True, slots=True)
class AppSettings:
    recordings_dir: Path = Path(".recordings")
    artifacts_dir: Path = Path(".reports")
    asr_url: str = "http://127.0.0.1:8101"
    diarization_url: str = "http://127.0.0.1:8102"
    emotion_url: str = "http://127.0.0.1:8103"
    qwen_base_url: str = "http://127.0.0.1:8000/v1"
    qwen_model: str = "qwen3.6-35b"
    qwen_report_timeout_seconds: int = 600
    qwen_report_max_tokens: int = 8192
    container_recordings_dir: str = "/data/recordings"
    rabbitmq_url: str | None = None
    rabbitmq_queue_name: str = "voice.recordings"

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(
            recordings_dir=Path(os.getenv("VOICE_RECORDINGS_DIR", ".recordings")),
            artifacts_dir=Path(os.getenv("VOICE_ARTIFACTS_DIR", ".reports")),
            asr_url=os.getenv("VOICE_ASR_URL", "http://127.0.0.1:8101"),
            diarization_url=os.getenv("VOICE_DIARIZATION_URL", "http://127.0.0.1:8102"),
            emotion_url=os.getenv("VOICE_EMOTION_URL", "http://127.0.0.1:8103"),
            qwen_base_url=os.getenv("VOICE_QWEN_BASE_URL", "http://127.0.0.1:8000/v1"),
            qwen_model=os.getenv("VOICE_QWEN_MODEL", "qwen3.6-35b"),
            qwen_report_timeout_seconds=int(os.getenv("VOICE_QWEN_REPORT_TIMEOUT_SECONDS", "600")),
            qwen_report_max_tokens=int(os.getenv("VOICE_QWEN_REPORT_MAX_TOKENS", "8192")),
            container_recordings_dir=os.getenv(
                "VOICE_CONTAINER_RECORDINGS_DIR",
                "/data/recordings",
            ),
            rabbitmq_url=os.getenv("VOICE_RABBITMQ_URL") or None,
            rabbitmq_queue_name=os.getenv("VOICE_RABBITMQ_QUEUE", "voice.recordings"),
        )


@dataclass(frozen=True, slots=True)
class Application:
    settings: AppSettings
    source: CallRecordingSource
    jobs: JobRepository
    artifacts: ArtifactStore
    queue: ProcessingQueue
    pipeline: CallProcessingService
    workspace: PipelineWorkspace
    worker: ProcessingWorker


def build_application(settings: AppSettings | None = None) -> Application:
    settings = settings or AppSettings.from_env()
    source = LocalDirectoryRecordingSource(settings.recordings_dir)
    inbox = LocalDirectoryRecordingInbox(settings.recordings_dir)
    jobs = LocalJobRepository(settings.artifacts_dir)
    artifacts = LocalArtifactStore(settings.artifacts_dir)
    queue = RabbitMQProcessingQueue(
        settings.rabbitmq_url or "amqp://guest:guest@localhost/",
        queue_name=settings.rabbitmq_queue_name,
    )
    audio_stager = MountedDirectoryAudioStager(
        host_directory=settings.recordings_dir,
        model_directory=settings.container_recordings_dir,
    )
    pipeline = CallProcessingService(
        source=source,
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
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: datetime.now(MSK),
        report_renderer=ReportLabReportRenderer(),
    )
    workspace = PipelineWorkspace(
        source=source,
        jobs=jobs,
        artifacts=artifacts,
        queue=queue,
        inbox=inbox,
        pipeline=pipeline,
        clock=lambda: datetime.now(MSK),
    )
    worker = ProcessingWorker(
        queue=queue,
        pipeline=pipeline,
        jobs=jobs,
        requeue_failed=False,
    )
    return Application(
        settings=settings,
        source=source,
        jobs=jobs,
        artifacts=artifacts,
        queue=queue,
        pipeline=pipeline,
        workspace=workspace,
        worker=worker,
    )


__all__ = ["AppSettings", "Application", "build_application"]
