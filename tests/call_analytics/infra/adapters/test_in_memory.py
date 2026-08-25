from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryCallRepository,
    InMemoryJobRepository,
    InMemoryRecordingSource,
)
from call_analytics.infra.ports import CallRecordingSourceError, Period
from domain import (
    AudioBlob,
    CallProcessingJob,
    CallRecording,
    ChannelLayout,
    DiarizedTranscript,
    DiscoveredCall,
    JobStatus,
    QueueIdentity,
    RecordingId,
    SourceRecordingIdentity,
    Transcript,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
RID = RecordingId("rec-1")


async def test_job_repository_roundtrip_and_query() -> None:
    repo = InMemoryJobRepository()
    job = CallProcessingJob.create("job-1", RID, datetime(2026, 1, 10, tzinfo=MSK))
    await repo.save(job)
    assert await repo.get("job-1") == job
    assert await repo.get("missing") is None
    pending = await repo.list_by_status(JobStatus.PENDING)
    assert list(pending) == [job]
    assert list(await repo.list_by_status(JobStatus.DONE)) == []


async def test_artifact_store_roundtrip() -> None:
    store = InMemoryArtifactStore()
    transcript = Transcript(recording_id=RID, language="ru", segments=(), full_text="")
    await store.save_transcript(transcript)
    assert await store.load_transcript(RID) == transcript
    assert await store.load_diarization(RID) is None
    diar = DiarizedTranscript(recording_id=RID, segments=())
    await store.save_diarization(diar)
    assert await store.load_diarization(RID) == diar


async def test_recording_source_fetch_and_missing() -> None:
    source = InMemoryRecordingSource()
    recording = CallRecording(
        id=RID,
        started_at=datetime(2026, 1, 10, 12, 0, tzinfo=MSK),
        duration=timedelta(minutes=5),
        channel_layout=ChannelLayout.STEREO,
    )
    blob = AudioBlob(data=b"x", codec="wav/gsm0610", layout=ChannelLayout.STEREO)
    source.add(recording, blob)

    assert await source.fetch_audio(RID) == blob
    listed = await source.list_recordings(
        Period(
            start=datetime(2026, 1, 1, tzinfo=MSK),
            end=datetime(2026, 2, 1, tzinfo=MSK),
        )
    )
    assert list(listed) == [recording]

    with pytest.raises(CallRecordingSourceError) as exc:
        await source.fetch_audio(RecordingId("missing"))
    assert exc.value.kind is CallRecordingSourceError.Kind.NOT_FOUND


async def test_call_repository_registers_and_skips_idempotently() -> None:
    repository = InMemoryCallRepository()
    recording = CallRecording(
        id=RID,
        started_at=datetime(2026, 1, 10, 12, 0, tzinfo=MSK),
        duration=timedelta(minutes=5),
        channel_layout=ChannelLayout.MONO,
        queue=QueueIdentity(extension="6500", name="Call_center"),
    )
    job = CallProcessingJob.create(RID.value, RID, recording.started_at)

    assert await repository.register(recording, job) is True
    assert await repository.register(recording, job) is False
    assert await repository.load_recording(RID) == recording

    skipped = DiscoveredCall(
        id=RecordingId("cdr:skipped"),
        started_at=recording.started_at,
        duration=timedelta(seconds=1),
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=recording.caller,
        operator=None,
        source_recording=SourceRecordingIdentity(acct_id=None),
    )
    await repository.register_skipped(skipped, "empty", recording.started_at)

    assert await repository.status(skipped.id) is JobStatus.SKIPPED_EMPTY
