from __future__ import annotations

import hashlib
import io
import wave
from collections import namedtuple
from pathlib import Path

import pytest

from call_analytics.infra.adapters.archive import FilesystemRecordingArchive
from call_analytics.service.ports import RecordingArchiveError
from domain import AudioBlob, ChannelLayout, RecordingId

pytestmark = pytest.mark.asyncio
RID = RecordingId("cdr:archive-001")
Usage = namedtuple("Usage", "total used free")


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x01\x00" * 1600)
    return buffer.getvalue()


WAV_AUDIO = AudioBlob(data=_wav(), codec="wav", layout=ChannelLayout.MONO)


async def test_archive_uses_hashed_layout_and_is_idempotent(tmp_path: Path) -> None:
    encoded: list[tuple[Path, Path, str]] = []

    def encoder(source: Path, target: Path, bitrate: str) -> None:
        encoded.append((source, target, bitrate))
        assert source.read_bytes() == WAV_AUDIO.data
        target.write_bytes(b"OggS-opus-test")

    archive = FilesystemRecordingArchive(
        tmp_path,
        reserve_bytes=1,
        encoder=encoder,
        probe=lambda path: path.read_bytes().startswith(b"OggS"),
        disk_usage=lambda path: Usage(total=1000, used=10, free=990),
    )

    first = await archive.store(RID, WAV_AUDIO)
    second = await archive.store(RID, WAV_AUDIO)
    located = await archive.locate(RID)

    digest = hashlib.sha256(RID.value.encode()).hexdigest()
    assert located is not None
    assert located.path == tmp_path / digest[:2] / f"{digest}.ogg"
    assert located.path.read_bytes() == b"OggS-opus-test"
    assert first == second
    assert first.size_bytes == len(b"OggS-opus-test")
    assert len(encoded) == 1
    assert encoded[0][2] == "24k"
    assert list(tmp_path.rglob("*.tmp")) == []
    assert list(tmp_path.rglob("*.input.wav")) == []


async def test_archive_refuses_write_below_reserve(tmp_path: Path) -> None:
    archive = FilesystemRecordingArchive(
        tmp_path,
        reserve_bytes=20,
        encoder=lambda source, target, bitrate: target.write_bytes(b"OggS"),
        probe=lambda path: True,
        disk_usage=lambda path: Usage(total=100, used=90, free=10),
    )

    with pytest.raises(RecordingArchiveError) as captured:
        await archive.store(RID, WAV_AUDIO)

    assert captured.value.kind == "ARCHIVE_CAPACITY"
    assert await archive.locate(RID) is None


async def test_archive_removes_temporary_files_after_encoding_failure(tmp_path: Path) -> None:
    def fail_encoding(source: Path, target: Path, bitrate: str) -> None:
        target.write_bytes(b"partial")
        raise RuntimeError("encoder failed")

    archive = FilesystemRecordingArchive(
        tmp_path,
        reserve_bytes=1,
        encoder=fail_encoding,
        probe=lambda path: False,
        disk_usage=lambda path: Usage(total=100, used=10, free=90),
    )

    with pytest.raises(RecordingArchiveError) as captured:
        await archive.store(RID, WAV_AUDIO)

    assert captured.value.kind == "ARCHIVE_ENCODING"
    assert list(tmp_path.rglob("*.ogg")) == []
    assert list(tmp_path.rglob("*.tmp")) == []
    assert list(tmp_path.rglob("*.input.wav")) == []


async def test_archive_rejects_output_that_fails_probe(tmp_path: Path) -> None:
    archive = FilesystemRecordingArchive(
        tmp_path,
        reserve_bytes=1,
        encoder=lambda source, target, bitrate: target.write_bytes(b"not-ogg"),
        probe=lambda path: False,
        disk_usage=lambda path: Usage(total=100, used=10, free=90),
    )

    with pytest.raises(RecordingArchiveError) as captured:
        await archive.store(RID, WAV_AUDIO)

    assert captured.value.kind == "ARCHIVE_ENCODING"
    assert await archive.locate(RID) is None


async def test_archive_reports_filesystem_usage(tmp_path: Path) -> None:
    archive = FilesystemRecordingArchive(
        tmp_path,
        reserve_bytes=2,
        encoder=lambda source, target, bitrate: target.write_bytes(b"OggS"),
        probe=lambda path: True,
        disk_usage=lambda path: Usage(total=100, used=85, free=15),
    )

    status = await archive.storage_status()

    assert status.total_bytes == 100
    assert status.used_bytes == 85
    assert status.free_bytes == 15
    assert status.used_percent == 85
    assert status.state == "warning"
