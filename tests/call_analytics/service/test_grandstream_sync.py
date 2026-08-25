from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryCallRepository,
    InMemoryJobRepository,
    InMemoryProcessingQueue,
    InMemorySyncRunRepository,
)
from call_analytics.service import AudioBackfillResult, GrandstreamSyncService, SyncResult
from call_analytics.service.ports import (
    ArchivedRecording,
    ArchivedRecordingFile,
    InvalidRecordingError,
    PreparedAudio,
    RecordingArchive,
    RecordingArchiveError,
    RecordingStorageStatus,
    RecordingWorkspace,
    TelephonyAccount,
    TelephonyGateway,
    TelephonyGatewayError,
)
from domain import (
    STAGE_ORDER,
    AudioBlob,
    CallerIdentity,
    CallProcessingJob,
    CallRecording,
    ChannelLayout,
    DiscoveredCall,
    JobStatus,
    OperatorIdentity,
    Period,
    QueueIdentity,
    RecordingId,
    SourceRecordingIdentity,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=MSK)
RID = RecordingId("cdr:group-001")
ACCOUNT = TelephonyAccount(id=14, extension="11198", fullname="Оператор")


def _call(operator: OperatorIdentity | None = None) -> DiscoveredCall:
    return DiscoveredCall(
        id=RID,
        started_at=NOW - timedelta(hours=1),
        duration=timedelta(seconds=91),
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=CallerIdentity(id="79000000001"),
        operator=operator or OperatorIdentity(id=14, extension="11198", name="Оператор"),
        source_recording=SourceRecordingIdentity(
            acct_id="901",
            filenames=("2026-08/call.wav",),
        ),
    )


class FakeTelephonyGateway(TelephonyGateway):
    def __init__(
        self,
        calls: Sequence[DiscoveredCall],
        recordings: dict[str, bytes | TelephonyGatewayError],
    ) -> None:
        self.calls = list(calls)
        self.recordings = recordings
        self.requested_period: Period | None = None
        self.download_count = 0
        self.closed = False

    async def list_accounts(self) -> Sequence[TelephonyAccount]:
        return [ACCOUNT]

    async def list_calls(
        self,
        period: Period,
        accounts: Sequence[TelephonyAccount],
    ) -> Sequence[DiscoveredCall]:
        assert accounts == [ACCOUNT]
        self.requested_period = period
        return self.calls

    async def recording_files(self, acct_id: str) -> tuple[str, ...]:
        return ("2026-08/available.wav",) if acct_id == "902" else ("2026-08/call.wav",)

    async def download_recording(self, filename: str) -> bytes:
        self.download_count += 1
        value = self.recordings[filename]
        if isinstance(value, TelephonyGatewayError):
            raise value
        return value

    async def close(self) -> None:
        self.closed = True


class FakeWorkspace(RecordingWorkspace):
    def __init__(self) -> None:
        self.audio: dict[str, AudioBlob] = {}

    async def prepare(self, call_id: RecordingId, parts: Sequence[bytes]) -> PreparedAudio:
        if not parts or any(not part for part in parts):
            raise InvalidRecordingError("recording contains an empty part")
        self.audio[call_id.value] = AudioBlob(
            data=b"".join(parts),
            codec="wav",
            layout=ChannelLayout.MONO,
        )
        return PreparedAudio(
            duration=timedelta(seconds=91),
            layout=ChannelLayout.MONO,
            codec="wav",
        )

    async def load_audio(self, call_id: RecordingId) -> AudioBlob:
        return self.audio[call_id.value]

    async def clear(self, call_id: RecordingId) -> None:
        self.audio.pop(call_id.value, None)

    async def clear_stale(self, older_than: datetime, protected=()) -> int:
        del older_than, protected
        return 0


class EmptyRecordingGateway(FakeTelephonyGateway):
    async def recording_files(self, acct_id: str) -> tuple[str, ...]:
        del acct_id
        return ()


class FakeArchive(RecordingArchive):
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events
        self.stored: set[RecordingId] = set()
        self.error: RecordingArchiveError | None = None

    async def store(self, recording_id: RecordingId, audio: AudioBlob) -> ArchivedRecording:
        if self.events is not None:
            self.events.append("archive")
        if self.error is not None:
            raise self.error
        self.stored.add(recording_id)
        return ArchivedRecording(recording_id, "audio/ogg", "opus", len(audio.data))

    async def locate(self, recording_id: RecordingId) -> ArchivedRecordingFile | None:
        if recording_id not in self.stored:
            return None
        return ArchivedRecordingFile(Path("/archive/test.ogg"), "audio/ogg", 12)

    async def storage_status(self) -> RecordingStorageStatus:
        return RecordingStorageStatus.from_usage(100, 10, 90, reserve_bytes=2)


class TrackingCallRepository(InMemoryCallRepository):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    async def register(self, recording, job):
        self._events.append("register")
        return await super().register(recording, job)


class TrackingQueue(InMemoryProcessingQueue):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    async def publish(self, recording_id: RecordingId) -> None:
        self._events.append("publish")
        await super().publish(recording_id)


def _build_service(
    gateway: FakeTelephonyGateway,
    archive: FakeArchive | None = None,
    events: list[str] | None = None,
    workspace: FakeWorkspace | None = None,
):
    calls = TrackingCallRepository(events) if events is not None else InMemoryCallRepository()
    jobs = InMemoryJobRepository()
    queue = TrackingQueue(events) if events is not None else InMemoryProcessingQueue()
    sync_runs = InMemorySyncRunRepository()
    service = GrandstreamSyncService(
        gateway=gateway,
        workspace=workspace or FakeWorkspace(),
        archive=archive or FakeArchive(events),
        calls=calls,
        jobs=jobs,
        sync_runs=sync_runs,
        queue=queue,
    )
    return service, calls, jobs, queue, sync_runs


async def test_sync_archives_before_register_and_publish() -> None:
    events: list[str] = []
    gateway = FakeTelephonyGateway([_call()], {"2026-08/call.wav": b"RIFFdemo"})
    service, _, _, _, _ = _build_service(gateway, events=events)

    result = await service.run_once(NOW)

    assert result.queued == 1
    assert events.index("archive") < events.index("register") < events.index("publish")


async def test_archive_failure_registers_failed_recording_and_does_not_publish() -> None:
    gateway = FakeTelephonyGateway([_call()], {"2026-08/call.wav": b"RIFFdemo"})
    archive = FakeArchive()
    archive.error = RecordingArchiveError("ARCHIVE_IO", "archive write failed")
    service, calls, jobs, queue, _ = _build_service(gateway, archive=archive)

    result = await service.run_once(NOW)

    assert result.failed == 1
    assert queue.published == ()
    assert await calls.status(RID) is JobStatus.FAILED
    failed = await jobs.get(RID.value)
    assert failed is not None
    assert failed.last_error == ("ARCHIVE_IO", "archive write failed")
    recording = await calls.load_recording(RID)
    assert recording is not None
    assert recording.source_recording is not None
    assert recording.source_recording.filenames == ("2026-08/call.wav",)


async def test_later_sync_retries_archive_failure_before_queueing() -> None:
    gateway = FakeTelephonyGateway([_call()], {"2026-08/call.wav": b"RIFFdemo"})
    archive = FakeArchive()
    archive.error = RecordingArchiveError("ARCHIVE_IO", "archive write failed")
    service, _, jobs, queue, _ = _build_service(gateway, archive=archive)
    await service.run_once(NOW)
    archive.error = None

    result = await service.run_once(NOW + timedelta(days=1))

    assert result.queued == 1
    assert queue.published == (RID,)
    restarted = await jobs.get(RID.value)
    assert restarted is not None
    assert restarted.status is JobStatus.PENDING
    assert RID in archive.stored


async def test_retry_clears_workspace_when_archive_still_fails() -> None:
    gateway = FakeTelephonyGateway([_call()], {"2026-08/call.wav": b"RIFFdemo"})
    archive = FakeArchive()
    archive.error = RecordingArchiveError("ARCHIVE_IO", "archive write failed")
    workspace = FakeWorkspace()
    service, _, _, queue, _ = _build_service(
        gateway,
        archive=archive,
        workspace=workspace,
    )
    await service.run_once(NOW)

    result = await service.run_once(NOW + timedelta(days=1))

    assert result.failed == 1
    assert queue.published == ()
    assert RID.value not in workspace.audio


async def test_backfill_skips_archived_and_continues_after_failure() -> None:
    already = CallRecording(
        id=RecordingId("cdr:already"),
        started_at=NOW,
        duration=timedelta(seconds=91),
        channel_layout=ChannelLayout.MONO,
        source_recording=SourceRecordingIdentity("910", ("already.wav",)),
    )
    fresh = replace(
        already,
        id=RecordingId("cdr:fresh"),
        started_at=NOW - timedelta(minutes=1),
        source_recording=SourceRecordingIdentity("911", ("fresh.wav",)),
    )
    broken = replace(
        already,
        id=RecordingId("cdr:broken"),
        started_at=NOW - timedelta(minutes=2),
        source_recording=SourceRecordingIdentity("912", ("broken.wav",)),
    )
    gateway = FakeTelephonyGateway(
        [],
        {
            "fresh.wav": b"RIFFfresh",
            "broken.wav": TelephonyGatewayError("SERVER", "hidden"),
        },
    )
    archive = FakeArchive()
    archive.stored.add(already.id)
    service, calls, _, _, _ = _build_service(gateway, archive=archive)
    for recording in (broken, fresh, already):
        done = replace(
            CallProcessingJob.create(recording.id.value, recording.id, recording.started_at),
            status=JobStatus.DONE,
            completed_stages=frozenset(STAGE_ORDER),
        )
        await calls.register(recording, done)

    result = await service.backfill_audio(limit=3)

    assert result == AudioBackfillResult(found=2, archived=1, skipped=1, failed=1)
    assert archive.stored == {already.id, fresh.id}
    assert gateway.closed is True


async def test_sync_uses_exact_thirty_day_window_and_queues_new_valid_call() -> None:
    gateway = FakeTelephonyGateway([_call()], {"2026-08/call.wav": b"RIFFdemo"})
    service, calls, jobs, queue, sync_runs = _build_service(gateway)

    result = await service.run_once(NOW)

    assert gateway.requested_period == Period(start=NOW - timedelta(days=30), end=NOW)
    assert result == SyncResult(discovered=1, queued=1, skipped=0, failed=0)
    assert queue.published == (RID,)
    stored_job = await jobs.get(RID.value)
    assert stored_job is not None
    assert stored_job.status is JobStatus.PENDING
    assert await calls.status(RID) is JobStatus.PENDING
    last_sync = await sync_runs.last()
    assert last_sync is not None
    assert last_sync.status == "done"
    assert gateway.closed is True


async def test_second_sync_does_not_download_or_queue_duplicate() -> None:
    gateway = FakeTelephonyGateway([_call()], {"2026-08/call.wav": b"RIFFdemo"})
    service, _, _, queue, _ = _build_service(gateway)
    await service.run_once(NOW)

    result = await service.run_once(NOW + timedelta(days=1))

    assert result.queued == 0
    assert gateway.download_count == 1
    assert queue.published == (RID,)


async def test_batch_limit_counts_new_calls_not_leading_duplicates() -> None:
    first = _call()
    second = replace(first, id=RecordingId("cdr:group-002"))
    gateway = FakeTelephonyGateway([first], {"2026-08/call.wav": b"RIFFdemo"})
    service, _, _, queue, _ = _build_service(gateway)
    await service.run_once(NOW)
    gateway.calls = [first, second]

    result = await service.run_once(NOW + timedelta(days=1), limit=1)

    assert result == SyncResult(discovered=1, queued=1, skipped=0, failed=0)
    assert queue.published == (RID, second.id)


async def test_empty_recording_is_registered_as_skipped() -> None:
    gateway = FakeTelephonyGateway([_call()], {"2026-08/call.wav": b""})
    service, calls, jobs, queue, _ = _build_service(gateway)

    result = await service.run_once(NOW)

    assert result.skipped == 1
    assert await calls.status(RID) is JobStatus.SKIPPED_EMPTY
    assert await jobs.get(RID.value) is None
    assert queue.published == ()


async def test_call_without_resolved_operator_is_failed_without_download() -> None:
    call = _call()
    call = DiscoveredCall(
        id=call.id,
        started_at=call.started_at,
        duration=call.duration,
        queue=call.queue,
        caller=call.caller,
        operator=None,
        source_recording=call.source_recording,
    )
    gateway = FakeTelephonyGateway([call], {"2026-08/call.wav": b"RIFFdemo"})
    service, calls, _, queue, _ = _build_service(gateway)

    result = await service.run_once(NOW)

    assert result.failed == 1
    assert await calls.status(RID) is JobStatus.FAILED
    assert gateway.download_count == 0
    assert queue.published == ()


async def test_unanswered_call_without_recording_is_skipped_not_failed() -> None:
    call = replace(
        _call(),
        operator=None,
        source_recording=SourceRecordingIdentity(acct_id="901", filenames=()),
    )
    gateway = EmptyRecordingGateway([call], {})
    service, calls, _, queue, _ = _build_service(gateway)

    result = await service.run_once(NOW)

    assert result == SyncResult(discovered=1, queued=0, skipped=1, failed=0)
    assert await calls.status(call.id) is JobStatus.SKIPPED_EMPTY
    assert gateway.download_count == 0
    assert queue.published == ()


async def test_missing_recording_skips_only_one_call_and_continues_batch() -> None:
    missing = _call()
    available = replace(
        missing,
        id=RecordingId("cdr:group-002"),
        source_recording=SourceRecordingIdentity(
            acct_id="902",
            filenames=("2026-08/available.wav",),
        ),
    )
    gateway = FakeTelephonyGateway(
        [missing, available],
        {
            "2026-08/call.wav": TelephonyGatewayError("NOT_FOUND", "hidden"),
            "2026-08/available.wav": b"RIFFdemo",
        },
    )
    service, calls, _, queue, _ = _build_service(gateway)

    result = await service.run_once(NOW)

    assert result == SyncResult(discovered=2, queued=1, skipped=1, failed=0)
    assert await calls.status(missing.id) is JobStatus.SKIPPED_EMPTY
    assert await calls.status(available.id) is JobStatus.PENDING
    assert queue.published == (available.id,)
