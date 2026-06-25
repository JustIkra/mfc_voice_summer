from __future__ import annotations

import json
from typing import Any

from call_analytics.service.ports import (
    ProcessingMessage,
    ProcessingQueue,
    ProcessingQueueError,
)
from domain import RecordingId


def encode_processing_message(recording_id: RecordingId) -> bytes:
    return json.dumps(
        {"recording_id": recording_id.value},
        ensure_ascii=False,
    ).encode("utf-8")


def decode_processing_message(body: bytes) -> RecordingId:
    payload = json.loads(body.decode("utf-8"))
    return RecordingId(str(payload["recording_id"]))


class RabbitMQProcessingQueue(ProcessingQueue):
    def __init__(
        self,
        url: str,
        queue_name: str = "voice.recordings",
        prefetch_count: int = 1,
    ) -> None:
        self._url = url
        self._queue_name = queue_name
        self._prefetch_count = prefetch_count
        self._connection: Any | None = None
        self._channel: Any | None = None
        self._queue: Any | None = None
        self._inflight: dict[str, Any] = {}

    async def publish(self, recording_id: RecordingId) -> None:
        try:
            await self._ensure_connected()
            aio_pika = self._aio_pika()
            assert self._channel is not None
            message = aio_pika.Message(
                body=encode_processing_message(recording_id),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=recording_id.value,
            )
            await self._channel.default_exchange.publish(
                message,
                routing_key=self._queue_name,
            )
        except Exception as error:
            raise ProcessingQueueError.unexpected(str(error)) from error

    async def get(self) -> ProcessingMessage | None:
        try:
            await self._ensure_connected()
            assert self._queue is not None
            incoming = await self._queue.get(fail=False)
            if incoming is None:
                return None
            delivery_tag = str(incoming.delivery_tag)
            self._inflight[delivery_tag] = incoming
            return ProcessingMessage(
                recording_id=decode_processing_message(incoming.body),
                delivery_tag=delivery_tag,
            )
        except Exception as error:
            raise ProcessingQueueError.unexpected(str(error)) from error

    async def ack(self, message: ProcessingMessage) -> None:
        incoming = self._lookup(message)
        await incoming.ack()
        self._inflight.pop(message.delivery_tag, None)

    async def reject(self, message: ProcessingMessage, requeue: bool) -> None:
        incoming = self._lookup(message)
        await incoming.reject(requeue=requeue)
        self._inflight.pop(message.delivery_tag, None)

    def _lookup(self, message: ProcessingMessage) -> Any:
        incoming = self._inflight.get(message.delivery_tag)
        if incoming is None:
            raise ProcessingQueueError.unexpected(
                f"delivery_tag {message.delivery_tag} is no longer available"
            )
        return incoming

    async def _ensure_connected(self) -> None:
        if self._queue is not None:
            return
        try:
            aio_pika = self._aio_pika()
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=self._prefetch_count)
            self._queue = await self._channel.declare_queue(
                self._queue_name,
                durable=True,
            )
        except Exception as error:
            raise ProcessingQueueError.connection(str(error)) from error

    def _aio_pika(self) -> Any:
        try:
            import aio_pika
        except ModuleNotFoundError as error:
            raise ProcessingQueueError.connection(
                "aio-pika is required for RabbitMQProcessingQueue"
            ) from error
        return aio_pika


__all__ = [
    "RabbitMQProcessingQueue",
    "decode_processing_message",
    "encode_processing_message",
]
