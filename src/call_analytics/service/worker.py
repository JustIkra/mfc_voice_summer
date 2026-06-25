from __future__ import annotations

from call_analytics.service.ports import CallProcessingPipeline, ProcessingQueue
from domain import JobStatus


class ProcessingWorker:
    def __init__(
        self,
        queue: ProcessingQueue,
        pipeline: CallProcessingPipeline,
        requeue_failed: bool = True,
    ) -> None:
        self._queue = queue
        self._pipeline = pipeline
        self._requeue_failed = requeue_failed

    @property
    def requeue_failed(self) -> bool:
        return self._requeue_failed

    async def run_once(self) -> bool:
        message = await self._queue.get()
        if message is None:
            return False

        job = await self._pipeline.process(message.recording_id)
        if job.status is JobStatus.DONE:
            await self._queue.ack(message)
        else:
            await self._queue.reject(message, requeue=self._requeue_failed)
        return True


__all__ = ["ProcessingWorker"]
