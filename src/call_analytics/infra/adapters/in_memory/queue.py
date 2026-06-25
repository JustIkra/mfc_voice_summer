from __future__ import annotations

from collections import deque

from call_analytics.infra.ports import ProcessingMessage, ProcessingQueue
from domain import RecordingId


class InMemoryProcessingQueue(ProcessingQueue):
    def __init__(self) -> None:
        self._messages: deque[ProcessingMessage] = deque()
        self._counter = 0
        self._acked: list[str] = []
        self._rejected: list[tuple[str, bool]] = []

    @property
    def acked(self) -> tuple[str, ...]:
        return tuple(self._acked)

    @property
    def rejected(self) -> tuple[tuple[str, bool], ...]:
        return tuple(self._rejected)

    async def publish(self, recording_id: RecordingId) -> None:
        self._counter += 1
        self._messages.append(
            ProcessingMessage(
                recording_id=recording_id,
                delivery_tag=str(self._counter),
            )
        )

    async def get(self) -> ProcessingMessage | None:
        if not self._messages:
            return None
        return self._messages.popleft()

    async def ack(self, message: ProcessingMessage) -> None:
        self._acked.append(message.recording_id.value)

    async def reject(self, message: ProcessingMessage, requeue: bool) -> None:
        self._rejected.append((message.recording_id.value, requeue))
        if requeue:
            self._messages.append(message)


__all__ = ["InMemoryProcessingQueue"]
