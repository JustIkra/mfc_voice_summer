from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
    InMemoryRecordingSource,
)
from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from call_analytics.service import CallProcessingService
from domain import AudioBlob, CallRecording, CallReport, ChannelLayout, RecordingId

MSK = timezone(timedelta(hours=3))


def moscow_now() -> datetime:
    """Текущее время в таймзоне Europe/Moscow."""
    return datetime.now(MSK)


async def run_demo(clock: Callable[[], datetime] = moscow_now) -> CallReport:
    """Прогнать пайплайн на синтетической записи и вернуть отчёт.

    Composition root: здесь noop/in_memory адаптеры собираются в
    `CallProcessingService`. Реальные адаптеры (Naumen, faster-whisper,
    SER, qwen) подставляются именно сюда — домен и сервис не меняются.
    """
    recording_id = RecordingId("demo-1")
    recording = CallRecording(
        id=recording_id,
        started_at=clock(),
        duration=timedelta(minutes=3),
        channel_layout=ChannelLayout.STEREO,
    )
    source = InMemoryRecordingSource()
    source.add(
        recording,
        AudioBlob(data=b"demo", codec="wav/gsm0610", layout=ChannelLayout.STEREO),
    )
    artifacts = InMemoryArtifactStore()
    service = CallProcessingService(
        source=source,
        transcriber=NoopTranscriber(recording_id),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=clock()),
        jobs=InMemoryJobRepository(),
        artifacts=artifacts,
        clock=clock,
    )

    await service.enqueue(recording)
    job = await service.process(recording_id)
    report = await artifacts.load_report(recording_id)
    if report is None:
        raise RuntimeError(f"отчёт не сформирован, статус job: {job.status.name}")
    return report


def _format_report(report: CallReport) -> str:
    return (
        f"Запись: {report.recording_id.value}\n"
        f"Удовлетворённость: {report.satisfaction.name}\n"
        f"Содержание: {report.summary}\n"
        f"Сгенерирован: {report.generated_at.isoformat()}"
    )


if __name__ == "__main__":
    print(_format_report(asyncio.run(run_demo())))
