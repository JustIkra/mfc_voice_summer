from __future__ import annotations

from abc import ABC, abstractmethod

from domain import CallProcessingJob, CallRecording, RecordingId


class CallProcessingPipeline(ABC):
    """Интерфейс use-case обработки звонка по стадиям."""

    @abstractmethod
    async def enqueue(self, recording: CallRecording) -> CallProcessingJob:
        """Поставить запись в обработку, создать job в PENDING."""

    @abstractmethod
    async def run_next_stage(self, job_id: str) -> CallProcessingJob:
        """Выполнить следующую незавершённую стадию job."""

    @abstractmethod
    async def process(self, recording_id: RecordingId) -> CallProcessingJob:
        """Прогнать пайплайн до завершения или первой ошибки."""

    @abstractmethod
    async def retry(self, job_id: str) -> CallProcessingJob:
        """Сбросить упавшую стадию в PENDING для повтора."""

    @abstractmethod
    async def cancel(self, job_id: str) -> CallProcessingJob:
        """Отменить ожидающую job."""

    @abstractmethod
    async def resume(self, job_id: str) -> CallProcessingJob:
        """Вернуть отменённую job в ожидание."""


__all__ = ["CallProcessingPipeline"]
