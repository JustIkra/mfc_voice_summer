from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import datetime

from call_analytics.service.ports import (
    CallProcessingPipeline,
    JobRepository,
    ProcessingMessage,
    ProcessingQueue,
    RecordingWorkspace,
)
from domain import JobStatus


class ProcessingWorker:
    def __init__(
        self,
        queue: ProcessingQueue,
        pipeline: CallProcessingPipeline,
        jobs: JobRepository,
        requeue_failed: bool = True,
        pending_reconcile_interval_seconds: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
        workspace: RecordingWorkspace | None = None,
        processing_timeout_seconds: float | None = None,
        max_stage_attempts: int = 8,
    ) -> None:
        self._queue = queue
        self._pipeline = pipeline
        self._jobs = jobs
        self._requeue_failed = requeue_failed
        self._pending_reconcile_interval_seconds = pending_reconcile_interval_seconds
        self._monotonic = monotonic
        self._next_pending_reconcile_at = 0.0
        self._workspace = workspace
        self._processing_timeout_seconds = processing_timeout_seconds
        self._max_stage_attempts = max_stage_attempts

    @property
    def requeue_failed(self) -> bool:
        return self._requeue_failed

    async def run_once(self) -> bool:
        message = await self._queue.get()
        if message is None:
            now = self._monotonic()
            if now < self._next_pending_reconcile_at:
                return False
            self._next_pending_reconcile_at = now + self._pending_reconcile_interval_seconds
            for job in await self._jobs.list_by_status(JobStatus.PENDING):
                await self._queue.publish(job.recording_id)
            return False

        try:
            processing = self._pipeline.process(message.recording_id)
            if self._processing_timeout_seconds is None:
                job = await processing
            else:
                job = await asyncio.wait_for(
                    processing,
                    timeout=self._processing_timeout_seconds,
                )
        except TimeoutError:
            await self._retry_timed_out(message)
            return True
        except Exception:
            if self._workspace is not None:
                await self._workspace.clear(message.recording_id)
            await self._queue.reject(message, requeue=self._requeue_failed)
            raise
        if job.status in {JobStatus.DONE, JobStatus.CANCELED, JobStatus.SKIPPED_EMPTY}:
            await self._queue.ack(message)
        else:
            await self._queue.reject(message, requeue=self._requeue_failed)
        return True

    async def _retry_timed_out(self, message: ProcessingMessage) -> None:
        job = await self._jobs.get(message.recording_id.value)
        await self._queue.reject(message, requeue=False)
        if job is None or job.status is not JobStatus.RUNNING:
            return
        stage = job.next_stage()
        attempts = job.attempts.get(stage, 0) if stage is not None else self._max_stage_attempts
        if stage is None or attempts >= self._max_stage_attempts:
            if stage is not None:
                await self._jobs.save(
                    job.fail_stage(
                        stage,
                        "PROCESSING_TIMEOUT",
                        "processing stage timed out and retry limit was exceeded",
                    )
                )
            if self._workspace is not None:
                await self._workspace.clear(job.recording_id)
            return
        recovered = job.recover_interrupted()
        await self._jobs.save(recovered)
        await self._queue.publish(recovered.recording_id)

    async def recover_interrupted_jobs(self) -> int:
        recovered = 0
        for job in await self._jobs.list_by_status(JobStatus.RUNNING):
            await self._jobs.save(job.recover_interrupted())
            await self._queue.publish(job.recording_id)
            recovered += 1
        return recovered

    async def recover_stale_jobs(
        self,
        older_than: datetime,
        max_stage_attempts: int,
    ) -> tuple[int, int]:
        requeued = exhausted = 0
        for job in await self._jobs.list_stale_running(older_than):
            stage = job.next_stage()
            attempts = job.attempts.get(stage, 0) if stage is not None else max_stage_attempts
            if stage is None or attempts >= max_stage_attempts:
                if stage is not None:
                    await self._jobs.save(
                        job.fail_stage(
                            stage,
                            "STALE_RETRY_EXHAUSTED",
                            "processing watchdog retry limit exceeded",
                        )
                    )
                if self._workspace is not None:
                    await self._workspace.clear(job.recording_id)
                exhausted += 1
                continue
            recovered = job.recover_interrupted()
            await self._jobs.save(recovered)
            await self._queue.publish(recovered.recording_id)
            requeued += 1
        return requeued, exhausted


__all__ = ["ProcessingWorker"]
