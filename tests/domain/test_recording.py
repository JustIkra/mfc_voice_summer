from datetime import datetime, timedelta, timezone

from domain.recording import (
    AudioBlob,
    CallerIdentity,
    CallerNameSource,
    CallRecording,
    ChannelLayout,
    DiscoveredCall,
    OperatorIdentity,
    QueueIdentity,
    RecordingId,
    SourceRecordingIdentity,
)

MSK = timezone(timedelta(hours=3))


def test_recording_is_immutable_value() -> None:
    rec = CallRecording(
        id=RecordingId("rec-1"),
        started_at=datetime(2026, 1, 10, 12, 0, tzinfo=MSK),
        duration=timedelta(minutes=5),
        channel_layout=ChannelLayout.STEREO,
    )
    assert rec.id == RecordingId("rec-1")
    assert rec.operator_id is None
    assert dict(rec.metadata) == {}


def test_audio_blob_carries_layout() -> None:
    blob = AudioBlob(data=b"\x00", codec="wav/gsm0610", layout=ChannelLayout.MONO)
    assert blob.layout is ChannelLayout.MONO


def test_recording_carries_typed_grandstream_snapshot() -> None:
    now = datetime(2026, 8, 22, 10, 30, tzinfo=MSK)
    recording = CallRecording(
        id=RecordingId("cdr:call-42"),
        started_at=now,
        duration=timedelta(seconds=91),
        channel_layout=ChannelLayout.MONO,
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=CallerIdentity(
            id="79001234567",
            name=None,
            name_source=CallerNameSource.UNKNOWN,
            name_confidence=0.0,
        ),
        operator=OperatorIdentity(id=14, extension="11198", name="Оператор"),
        source_recording=SourceRecordingIdentity(
            acct_id="901",
            filenames=("2026-08/call.wav",),
        ),
    )

    assert recording.operator is not None
    assert recording.operator.extension == "11198"
    assert recording.source_recording is not None
    assert recording.source_recording.filenames == ("2026-08/call.wav",)


def test_discovered_call_does_not_require_audio_layout() -> None:
    discovered = DiscoveredCall(
        id=RecordingId("cdr:call-42"),
        started_at=datetime(2026, 8, 22, 10, 30, tzinfo=MSK),
        duration=timedelta(seconds=91),
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=CallerIdentity(id="79001234567"),
        operator=None,
        source_recording=SourceRecordingIdentity(acct_id=None),
    )

    assert discovered.source_recording.acct_id is None
