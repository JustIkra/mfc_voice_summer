from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum, auto

from call_analytics.service.ports import (
    CallRepository,
    InvalidRecordingError,
    JobRepository,
    ProcessingQueue,
    RecordingWorkspace,
    SyncRunRepository,
    TelephonyGateway,
)
from domain import CallProcessingJob, CallRecording, DiscoveredCall, Period

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncResult:
    discovered: int
    queued: int
    skipped: int
    failed: int


class IngestOutcome(Enum):
    DUPLICATE = auto()
    QUEUED = auto()
    SKIPPED = auto()
    FAILED = auto()


class GrandstreamSyncService:
    def __init__(
        self,
        gateway: TelephonyGateway,
        workspace: RecordingWorkspace,
        calls: CallRepository,
        jobs: JobRepository,
        sync_runs: SyncRunRepository,
        queue: ProcessingQueue,
        queue_extension: str = "6500",
        max_attempts: int = 5,
    ) -> None:
        self._gateway = gateway
        self._workspace = workspace
        self._calls = calls
        self._jobs = jobs
        self._sync_runs = sync_runs
        self._queue = queue
        self._queue_extension = queue_extension
        self._max_attempts = max_attempts

    async def run_once(self, now: datetime, limit: int | None = None) -> SyncResult:
        period = Period(start=now - timedelta(days=30), end=now)
        run_id = await self._sync_runs.start(period, now)
        if run_id is None:
            return SyncResult(discovered=0, queued=0, skipped=0, failed=0)
        discovered = queued = skipped = failed = 0
        try:
            accounts = await self._gateway.list_accounts()
            calls = await self._gateway.list_calls(period, accounts)
            for call in calls:
                if call.queue.extension != self._queue_extension:
                    continue
                outcome = await self._ingest(call, now)
                if outcome is IngestOutcome.DUPLICATE:
                    continue
                discovered += 1
                if outcome is IngestOutcome.QUEUED:
                    queued += 1
                elif outcome is IngestOutcome.SKIPPED:
                    skipped += 1
                elif outcome is IngestOutcome.FAILED:
                    failed += 1
                if limit is not None and discovered >= limit:
                    break

            for recording in await self._calls.list_retryable(self._max_attempts):
                if limit is not None and queued >= limit:
                    break
                outcome = await self._retry(recording)
                if outcome is IngestOutcome.QUEUED:
                    queued += 1
                elif outcome is IngestOutcome.SKIPPED:
                    skipped += 1
                elif outcome is IngestOutcome.FAILED:
                    failed += 1
        except Exception as error:
            await self._sync_runs.finish(
                run_id,
                finished_at=now,
                status="failed",
                discovered=discovered,
                queued=queued,
                skipped=skipped,
                failed=failed + 1,
                error_kind=type(error).__name__,
                error_message="synchronization failed",
            )
            raise
        else:
            await self._sync_runs.finish(
                run_id,
                finished_at=now,
                status="done",
                discovered=discovered,
                queued=queued,
                skipped=skipped,
                failed=failed,
            )
            return SyncResult(
                discovered=discovered,
                queued=queued,
                skipped=skipped,
                failed=failed,
            )
        finally:
            try:
                await self._gateway.close()
            except Exception:
                LOGGER.warning("Grandstream logout failed", exc_info=True)

    async def _ingest(self, call: DiscoveredCall, now: datetime) -> IngestOutcome:
        if await self._calls.contains(call.id):
            return IngestOutcome.DUPLICATE
        if call.operator is None:
            await self._calls.register_failed(
                call,
                "OPERATOR_NOT_RESOLVED",
                "answered queue operator is not present in listAccount",
                now,
            )
            return IngestOutcome.FAILED
        acct_id = call.source_recording.acct_id
        if acct_id is None:
            await self._calls.register_skipped(call, "recording CDR id is absent", now)
            return IngestOutcome.SKIPPED
        filenames = await self._gateway.recording_files(acct_id)
        if not filenames:
            filenames = call.source_recording.filenames
        if not filenames:
            await self._calls.register_skipped(call, "recording file is absent", now)
            return IngestOutcome.SKIPPED
        parts = [await self._gateway.download_recording(filename) for filename in filenames]
        try:
            prepared = await self._workspace.prepare(call.id, parts)
        except InvalidRecordingError as error:
            await self._calls.register_skipped(call, str(error), now)
            return IngestOutcome.SKIPPED
        recording = CallRecording(
            id=call.id,
            started_at=call.started_at,
            duration=prepared.duration,
            channel_layout=prepared.layout,
            queue=call.queue,
            caller=call.caller,
            operator=call.operator,
            source_recording=replace(call.source_recording, filenames=filenames),
        )
        job = CallProcessingJob.create(recording.id.value, recording.id, now)
        if not await self._calls.register(recording, job):
            await self._workspace.clear(recording.id)
            return IngestOutcome.DUPLICATE
        await self._jobs.save(job)
        await self._queue.publish(recording.id)
        return IngestOutcome.QUEUED

    async def _retry(self, recording: CallRecording) -> IngestOutcome:
        job = await self._jobs.get(recording.id.value)
        source = recording.source_recording
        if job is None or source is None or source.acct_id is None:
            return IngestOutcome.FAILED
        filenames = source.filenames or await self._gateway.recording_files(source.acct_id)
        if not filenames:
            await self._calls.mark_skipped_empty(recording.id, "recording file is absent")
            return IngestOutcome.SKIPPED
        parts = [await self._gateway.download_recording(filename) for filename in filenames]
        try:
            await self._workspace.prepare(recording.id, parts)
        except InvalidRecordingError as error:
            await self._calls.mark_skipped_empty(recording.id, str(error))
            return IngestOutcome.SKIPPED
        restarted = job.restart()
        await self._jobs.save(restarted)
        await self._queue.publish(recording.id)
        return IngestOutcome.QUEUED


__all__ = ["GrandstreamSyncService", "SyncResult"]
