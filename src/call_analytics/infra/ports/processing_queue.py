from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto

from domain import RecordingId


class ProcessingQueueError(Exception):
    class Kind(Enum):
        CONNECTION = auto()
        TIMEOUT = auto()
        UNEXPECTED = auto()

    def __init__(self, kind: ProcessingQueueError.Kind, message: str) -> None:
        self.kind = kind
        super().__init__(f"{kind.name}: {message}")

    @classmethod
    def connection(cls, message: str) -> ProcessingQueueError:
        return cls(cls.Kind.CONNECTION, message)

    @classmethod
    def timeout(cls, message: str) -> ProcessingQueueError:
        return cls(cls.Kind.TIMEOUT, message)

    @classmethod
    def unexpected(cls, message: str) -> ProcessingQueueError:
        return cls(cls.Kind.UNEXPECTED, message)


@dataclass(frozen=True, slots=True)
class ProcessingMessage:
    recording_id: RecordingId
    delivery_tag: str


class ProcessingQueue(ABC):
    @abstractmethod
    async def publish(self, recording_id: RecordingId) -> None:
        """Publish a recording id for asynchronous processing."""

    @abstractmethod
    async def get(self) -> ProcessingMessage | None:
        """Return one message or None when the queue is empty."""

    @abstractmethod
    async def ack(self, message: ProcessingMessage) -> None:
        """Mark a message as successfully processed."""

    @abstractmethod
    async def reject(self, message: ProcessingMessage, requeue: bool) -> None:
        """Reject a message after failed processing."""


__all__ = ["ProcessingMessage", "ProcessingQueue", "ProcessingQueueError"]
