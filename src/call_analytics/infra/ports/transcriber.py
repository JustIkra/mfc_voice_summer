from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import AudioBlob, Transcript


class TranscriberError(Exception):
    """Контрактная ошибка `Transcriber` (faster-whisper и т.п.)."""

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        INVALID_FORMAT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: TranscriberError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def invalid_format(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.INVALID_FORMAT, message)

    @classmethod
    def unexpected(cls, message: str) -> TranscriberError:
        return cls(cls.Kind.UNEXPECTED, message)


class Transcriber(ABC):
    """Абстрактный порт распознавания речи в текст."""

    @abstractmethod
    async def transcribe(self, audio: AudioBlob) -> Transcript:
        """Распознать аудио в `Transcript` с тайм-кодами по сегментам."""


__all__ = ["Transcriber", "TranscriberError"]
