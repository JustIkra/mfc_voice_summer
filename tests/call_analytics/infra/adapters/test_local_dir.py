from __future__ import annotations

import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.local_dir import (
    LocalDirectoryRecordingInbox,
    LocalDirectoryRecordingSource,
)
from call_analytics.infra.ports import CallRecordingSourceError, Period
from domain import ChannelLayout, RecordingId

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))

MONO_NAME = "q6500-FreeSWITCH-20260302-080314-1772427789.149782-11198"
STEREO_NAME = "q6500-79009337234-20250630-134146-1751280101.328447-11196"


def _make_wav(
    path: Path, nchannels: int, framerate: int = 8000, frames: int = 8000
) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(nchannels)
        wav.setsampwidth(2)
        wav.setframerate(framerate)
        wav.writeframes(b"\x00\x00" * frames * nchannels)


def _wide_period() -> Period:
    return Period(
        start=datetime(2024, 1, 1, tzinfo=MSK),
        end=datetime(2027, 1, 1, tzinfo=MSK),
    )


async def test_list_recordings_reads_header_and_name(tmp_path: Path) -> None:
    _make_wav(tmp_path / f"{MONO_NAME}.wav", nchannels=1)
    _make_wav(tmp_path / f"{STEREO_NAME}.wav", nchannels=2)
    source = LocalDirectoryRecordingSource(tmp_path)

    recordings = await source.list_recordings(_wide_period())

    by_id = {rec.id.value: rec for rec in recordings}
    assert set(by_id) == {MONO_NAME, STEREO_NAME}

    mono = by_id[MONO_NAME]
    assert mono.channel_layout is ChannelLayout.MONO
    assert mono.duration == timedelta(seconds=1)
    assert mono.started_at == datetime.fromtimestamp(1772427789.149782, MSK)
    assert mono.metadata["filename"] == f"{MONO_NAME}.wav"

    stereo = by_id[STEREO_NAME]
    assert stereo.channel_layout is ChannelLayout.STEREO
    assert stereo.started_at == datetime.fromtimestamp(1751280101.328447, MSK)


async def test_list_recordings_reads_nested_audio_directories(tmp_path: Path) -> None:
    nested = tmp_path / "2026-03" / f"{MONO_NAME}.wav"
    nested.parent.mkdir()
    _make_wav(nested, nchannels=1)
    source = LocalDirectoryRecordingSource(tmp_path)

    recordings = await source.list_recordings(_wide_period())
    recording = recordings[0]
    blob = await source.fetch_audio(recording.id)

    assert recording.id.value != MONO_NAME
    assert recording.metadata["filename"] == f"2026-03/{MONO_NAME}.wav"
    assert blob.data == nested.read_bytes()


async def test_period_filter_excludes_outside(tmp_path: Path) -> None:
    _make_wav(tmp_path / f"{MONO_NAME}.wav", nchannels=1)
    source = LocalDirectoryRecordingSource(tmp_path)

    narrow = Period(
        start=datetime(2026, 3, 1, tzinfo=MSK),
        end=datetime(2026, 3, 2, tzinfo=MSK),
    )
    assert await source.list_recordings(narrow) == []


async def test_list_recordings_skips_corrupt_wav_files(tmp_path: Path) -> None:
    _make_wav(tmp_path / f"{MONO_NAME}.wav", nchannels=1)
    (tmp_path / "broken.wav").write_bytes(b"not a wav")
    source = LocalDirectoryRecordingSource(tmp_path)

    recordings = await source.list_recordings(_wide_period())

    assert [recording.id.value for recording in recordings] == [MONO_NAME]


async def test_fetch_audio_returns_bytes_and_layout(tmp_path: Path) -> None:
    path = tmp_path / f"{STEREO_NAME}.wav"
    _make_wav(path, nchannels=2)
    source = LocalDirectoryRecordingSource(tmp_path)

    blob = await source.fetch_audio(RecordingId(STEREO_NAME))

    assert blob.data == path.read_bytes()
    assert blob.codec == "wav"
    assert blob.layout is ChannelLayout.STEREO


async def test_fetch_audio_missing_is_not_found(tmp_path: Path) -> None:
    source = LocalDirectoryRecordingSource(tmp_path)
    with pytest.raises(CallRecordingSourceError) as exc:
        await source.fetch_audio(RecordingId("nope"))
    assert exc.value.kind is CallRecordingSourceError.Kind.NOT_FOUND


async def test_recording_inbox_saves_uploaded_wav(tmp_path: Path) -> None:
    uploaded = tmp_path / "source.wav"
    _make_wav(uploaded, nchannels=1)
    inbox = LocalDirectoryRecordingInbox(tmp_path)

    recording = await inbox.save_wav("../new-call.wav", uploaded.read_bytes())

    assert recording.id.value == "new-call"
    assert recording.metadata["filename"] == "new-call.wav"
    assert (tmp_path / "new-call.wav").is_file()
    assert not (tmp_path.parent / "new-call.wav").exists()


async def test_recording_inbox_removes_invalid_wav_upload(tmp_path: Path) -> None:
    inbox = LocalDirectoryRecordingInbox(tmp_path)

    with pytest.raises(CallRecordingSourceError):
        await inbox.save_wav("bad.wav", b"not a wav")

    assert not (tmp_path / "bad.wav").exists()


async def test_recording_inbox_removes_partial_file_when_upload_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inbox = LocalDirectoryRecordingInbox(tmp_path)
    original_write_bytes = Path.write_bytes

    def failing_write_bytes(path: Path, data: bytes) -> int:
        original_write_bytes(path, data[:4])
        raise OSError("upload interrupted")

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)

    with pytest.raises(OSError, match="upload interrupted"):
        await inbox.save_wav("bad.wav", b"RIFFdemo")

    assert list(tmp_path.iterdir()) == []


async def test_recording_inbox_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    existing = tmp_path / "call.wav"
    _make_wav(existing, nchannels=1, frames=8000)
    incoming = tmp_path / "incoming.wav"
    _make_wav(incoming, nchannels=1, frames=16000)
    inbox = LocalDirectoryRecordingInbox(tmp_path)

    recording = await inbox.save_wav("call.wav", incoming.read_bytes())

    assert recording.id.value == "call-1"
    assert (tmp_path / "call.wav").read_bytes() == existing.read_bytes()
    assert (tmp_path / "call-1.wav").is_file()
