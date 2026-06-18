from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import AudioBlob, DiarizedTranscript, Transcript


class SpeakerDiarizerError(Exception):
    """Контрактная ошибка `SpeakerDiarizer`.

    Реализация сама решает стратегию: разбивка по стерео-каналам
    (оператор=0/клиент=1) либо ML-диаризация для моно. Сервис разницы
    не видит.
    """

    class Kind(Enum):
        INVALID_FORMAT = auto()
        TIMEOUT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: SpeakerDiarizerError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def invalid_format(cls, message: str) -> SpeakerDiarizerError:
        return cls(cls.Kind.INVALID_FORMAT, message)

    @classmethod
    def timeout(cls, message: str) -> SpeakerDiarizerError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def unexpected(cls, message: str) -> SpeakerDiarizerError:
        return cls(cls.Kind.UNEXPECTED, message)


class SpeakerDiarizer(ABC):
    """Абстрактный порт разметки говорящих (оператор/клиент)."""

    @abstractmethod
    async def diarize(
        self, audio: AudioBlob, transcript: Transcript
    ) -> DiarizedTranscript:
        """Привязать сегменты транскрипта к ролям говорящих."""


__all__ = ["SpeakerDiarizer", "SpeakerDiarizerError"]
