from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from domain import CallProcessingJob, JobStatus


class JobRepository(ABC):
    """Абстрактный порт персистенции машины состояний job."""

    @abstractmethod
    async def save(self, job: CallProcessingJob) -> None:
        """Сохранить (upsert) состояние job."""

    @abstractmethod
    async def get(self, job_id: str) -> CallProcessingJob | None:
        """Прочитать job по идентификатору или `None`."""

    @abstractmethod
    async def list_by_status(self, status: JobStatus) -> Sequence[CallProcessingJob]:
        """Список job в указанном статусе."""


__all__ = ["JobRepository"]
