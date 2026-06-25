from __future__ import annotations

from call_analytics.service.ports import (
    CallProcessingPipeline,
    JobRepository,
    ProcessingQueue,
)
from domain import JobStatus


class ProcessingWorker:
    def __init__(
        self,
        queue: ProcessingQueue,
        pipeline: CallProcessingPipeline,
        jobs: JobRepository,
        requeue_failed: bool = True,
    ) -> None:
        self._queue = queue
        self._pipeline = pipeline
        self._jobs = jobs
        self._requeue_failed = requeue_failed

    @property
    def requeue_failed(self) -> bool:
        return self._requeue_failed

    async def run_once(self) -> bool:
        message = await self._queue.get()
        if message is None:
            return False

        try:
            job = await self._pipeline.process(message.recording_id)
        except Exception:
            await self._queue.reject(message, requeue=self._requeue_failed)
            raise
        if job.status is JobStatus.DONE:
            await self._queue.ack(message)
        else:
            await self._queue.reject(message, requeue=self._requeue_failed)
        return True

    async def recover_interrupted_jobs(self) -> int:
        recovered = 0
        for job in await self._jobs.list_by_status(JobStatus.RUNNING):
            await self._jobs.save(job.recover_interrupted())
            await self._queue.publish(job.recording_id)
            recovered += 1
        return recovered


__all__ = ["ProcessingWorker"]
