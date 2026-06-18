from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import AudioBlob, DiarizedTranscript, EmotionAnalysis


class EmotionRecognizerError(Exception):
    """Контрактная ошибка `EmotionRecognizer` (SER-модель)."""

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        INVALID_FORMAT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: EmotionRecognizerError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def invalid_format(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.INVALID_FORMAT, message)

    @classmethod
    def unexpected(cls, message: str) -> EmotionRecognizerError:
        return cls(cls.Kind.UNEXPECTED, message)


class EmotionRecognizer(ABC):
    """Абстрактный порт распознавания эмоций по сегментам речи."""

    @abstractmethod
    async def recognize(
        self, audio: AudioBlob, diarized: DiarizedTranscript
    ) -> EmotionAnalysis:
        """Определить эмоции для сегментов размеченного транскрипта."""


__all__ = ["EmotionRecognizer", "EmotionRecognizerError"]
