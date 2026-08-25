from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryCallRepository,
    InMemoryJobRepository,
    InMemoryProcessingQueue,
    InMemorySyncRunRepository,
)
from call_analytics.service import GrandstreamSyncService, SyncResult
from call_analytics.service.ports import (
    InvalidRecordingError,
    PreparedAudio,
    RecordingWorkspace,
    TelephonyAccount,
    TelephonyGateway,
    TelephonyGatewayError,
)
from domain import (
    AudioBlob,
    CallerIdentity,
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


def _build_service(gateway: FakeTelephonyGateway):
    calls = InMemoryCallRepository()
    jobs = InMemoryJobRepository()
    queue = InMemoryProcessingQueue()
    sync_runs = InMemorySyncRunRepository()
    service = GrandstreamSyncService(
        gateway=gateway,
        workspace=FakeWorkspace(),
        calls=calls,
        jobs=jobs,
        sync_runs=sync_runs,
        queue=queue,
    )
    return service, calls, jobs, queue, sync_runs


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
