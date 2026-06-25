from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from call_analytics.infra.adapters.local_dir import (
    LocalArtifactStore,
    LocalDirectoryRecordingSource,
    LocalJobRepository,
)
from call_analytics.infra.adapters.model_api import (
    QwenReportGenerator,
    VoiceModelDiarizer,
    VoiceModelEmotionRecognizer,
    VoiceModelTranscriber,
)
from call_analytics.infra.adapters.queue import RabbitMQProcessingQueue
from call_analytics.infra.adapters.reporting import ReportLabReportRenderer
from call_analytics.infra.ports import (
    ArtifactStore,
    CallRecordingSource,
    JobRepository,
    ProcessingQueue,
)
from call_analytics.service import CallProcessingService, ProcessingWorker

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
    worker: ProcessingWorker


def build_application(settings: AppSettings | None = None) -> Application:
    settings = settings or AppSettings.from_env()
    source = LocalDirectoryRecordingSource(settings.recordings_dir)
    jobs = LocalJobRepository(settings.artifacts_dir)
    artifacts = LocalArtifactStore(settings.artifacts_dir)
    queue = RabbitMQProcessingQueue(
        settings.rabbitmq_url or "amqp://guest:guest@localhost/",
        queue_name=settings.rabbitmq_queue_name,
    )
    pipeline = CallProcessingService(
        source=source,
        transcriber=VoiceModelTranscriber(
            base_url=settings.asr_url,
            container_recordings_dir=settings.container_recordings_dir,
        ),
        diarizer=VoiceModelDiarizer(
            base_url=settings.diarization_url,
            container_recordings_dir=settings.container_recordings_dir,
        ),
        emotion_recognizer=VoiceModelEmotionRecognizer(
            base_url=settings.emotion_url,
            container_recordings_dir=settings.container_recordings_dir,
        ),
        report_generator=QwenReportGenerator(
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
            clock=lambda: datetime.now(MSK),
        ),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: datetime.now(MSK),
        report_renderer=ReportLabReportRenderer(),
    )
    return Application(
        settings=settings,
        source=source,
        jobs=jobs,
        artifacts=artifacts,
        queue=queue,
        pipeline=pipeline,
        worker=ProcessingWorker(queue=queue, pipeline=pipeline),
    )


__all__ = ["AppSettings", "Application", "build_application"]
