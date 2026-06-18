from datetime import datetime, timedelta, timezone

from domain.recording import AudioBlob, CallRecording, ChannelLayout, RecordingId

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
