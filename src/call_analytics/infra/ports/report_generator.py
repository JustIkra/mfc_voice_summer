from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto

from domain import CallReport, DiarizedTranscript, EmotionAnalysis, Transcript


class ReportGeneratorError(Exception):
    """Контрактная ошибка `ReportGenerator` (qwen и т.п.)."""

    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        RATE_LIMIT = auto()
        INVALID_REQUEST = auto()
        SERVER = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: ReportGeneratorError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def rate_limit(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.RATE_LIMIT, message)

    @classmethod
    def invalid_request(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.INVALID_REQUEST, message)

    @classmethod
    def server(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.SERVER, message)

    @classmethod
    def unexpected(cls, message: str) -> ReportGeneratorError:
        return cls(cls.Kind.UNEXPECTED, message)


class ReportGenerator(ABC):
    """Абстрактный порт генерации отчёта об удовлетворённости и содержании."""

    @abstractmethod
    async def generate(
        self,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> CallReport:
        """Построить `CallReport` по размеченному транскрипту и эмоциям."""


__all__ = ["ReportGenerator", "ReportGeneratorError"]
