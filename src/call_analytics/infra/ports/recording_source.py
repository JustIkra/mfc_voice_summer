from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from domain import AudioBlob, CallRecording, RecordingId


@dataclass(frozen=True, slots=True)
class Period:
    start: datetime
    end: datetime


class CallRecordingSourceError(Exception):
    """Контрактная ошибка `CallRecordingSource`.

    Адаптер источника записей (Naumen и т.п.) обязан заворачивать
    провайдер-специфичные исключения в этот класс. Вид — в `Kind`.
    """

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        NOT_FOUND = auto()
        AUTH = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: CallRecordingSourceError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def not_found(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.NOT_FOUND, message)

    @classmethod
    def auth(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.AUTH, message)

    @classmethod
    def unexpected(cls, message: str) -> CallRecordingSourceError:
        return cls(cls.Kind.UNEXPECTED, message)


class CallRecordingSource(ABC):
    """Абстрактный порт источника записей звонков (Naumen-экспорт)."""

    @abstractmethod
    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        """Список записей за период."""

    @abstractmethod
    async def fetch_audio(self, recording_id: RecordingId) -> AudioBlob:
        """Скачать аудио записи по идентификатору."""


__all__ = ["CallRecordingSource", "CallRecordingSourceError", "Period"]
