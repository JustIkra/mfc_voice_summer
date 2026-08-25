from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from call_analytics.service.ports import (
    ArchivedRecording,
    ArchivedRecordingFile,
    RecordingArchive,
    RecordingArchiveError,
    RecordingStorageStatus,
)
from domain import AudioBlob, RecordingId

Encoder = Callable[[Path, Path, str], None]
Probe = Callable[[Path], bool]


class DiskUsageResult(Protocol):
    total: int
    used: int
    free: int


DiskUsage = Callable[[Path], DiskUsageResult]


class FilesystemRecordingArchive(RecordingArchive):
    def __init__(
        self,
        root: Path,
        bitrate: str = "24k",
        reserve_bytes: int = 2 * 1024**3,
        encoder: Encoder | None = None,
        probe: Probe | None = None,
        disk_usage: DiskUsage | None = None,
    ) -> None:
        self._root = root
        self._bitrate = bitrate
        self._reserve_bytes = reserve_bytes
        self._encoder = encoder or _encode_opus
        self._probe = probe or _probe_ogg
        self._disk_usage = disk_usage or shutil.disk_usage

    async def store(
        self,
        recording_id: RecordingId,
        audio: AudioBlob,
    ) -> ArchivedRecording:
        return await asyncio.to_thread(self._store, recording_id, audio)

    async def locate(self, recording_id: RecordingId) -> ArchivedRecordingFile | None:
        return await asyncio.to_thread(self._locate, recording_id)

    async def storage_status(self) -> RecordingStorageStatus:
        return await asyncio.to_thread(self._storage_status)

    def archive_path(self, recording_id: RecordingId) -> Path:
        digest = hashlib.sha256(recording_id.value.encode()).hexdigest()
        return self._root / digest[:2] / f"{digest}.ogg"

    def _store(self, recording_id: RecordingId, audio: AudioBlob) -> ArchivedRecording:
        final = self.archive_path(recording_id)
        located = self._locate(recording_id)
        if located is not None:
            return _stored(recording_id, located.size_bytes)
        try:
            usage = self._disk_usage(self._root)
        except OSError as error:
            raise RecordingArchiveError(
                "ARCHIVE_IO",
                "archive filesystem is unavailable",
            ) from error
        if usage.free < self._reserve_bytes:
            raise RecordingArchiveError("ARCHIVE_CAPACITY", "recording archive reserve reached")

        token = uuid.uuid4().hex
        directory = final.parent
        source = directory / f".{final.stem}.{token}.input.wav"
        temporary = directory / f".{final.stem}.{token}.tmp"
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o755)
            source.write_bytes(audio.data)
            source.chmod(0o600)
            try:
                self._encoder(source, temporary, self._bitrate)
            except RecordingArchiveError:
                raise
            except Exception as error:
                raise RecordingArchiveError(
                    "ARCHIVE_ENCODING",
                    "recording archive encoding failed",
                ) from error
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise RecordingArchiveError(
                    "ARCHIVE_ENCODING",
                    "recording archive output is empty",
                )
            try:
                valid = self._probe(temporary)
            except Exception as error:
                raise RecordingArchiveError(
                    "ARCHIVE_ENCODING",
                    "recording archive validation failed",
                ) from error
            if not valid:
                raise RecordingArchiveError(
                    "ARCHIVE_ENCODING",
                    "recording archive output is invalid",
                )
            temporary.chmod(0o644)
            os.replace(temporary, final)
            return _stored(recording_id, final.stat().st_size)
        except RecordingArchiveError:
            raise
        except OSError as error:
            raise RecordingArchiveError("ARCHIVE_IO", "recording archive write failed") from error
        finally:
            source.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)

    def _locate(self, recording_id: RecordingId) -> ArchivedRecordingFile | None:
        path = self.archive_path(recording_id)
        try:
            if not path.is_file() or path.stat().st_size <= 0 or not self._probe(path):
                return None
            return ArchivedRecordingFile(
                path=path,
                mime_type="audio/ogg",
                size_bytes=path.stat().st_size,
            )
        except OSError:
            return None

    def _storage_status(self) -> RecordingStorageStatus:
        try:
            usage = self._disk_usage(self._root)
        except OSError as error:
            raise RecordingArchiveError(
                "ARCHIVE_IO",
                "archive filesystem is unavailable",
            ) from error
        return RecordingStorageStatus.from_usage(
            usage.total,
            usage.used,
            usage.free,
            self._reserve_bytes,
        )


def _stored(recording_id: RecordingId, size_bytes: int) -> ArchivedRecording:
    return ArchivedRecording(
        recording_id=recording_id,
        mime_type="audio/ogg",
        codec="opus",
        size_bytes=size_bytes,
    )


def _encode_opus(source: Path, target: Path, bitrate: str) -> None:
    result = _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libopus",
            "-b:a",
            bitrate,
            "-vbr",
            "on",
            "-application",
            "voip",
            "-f",
            "ogg",
            str(target),
        ]
    )
    if result.returncode != 0:
        raise RecordingArchiveError("ARCHIVE_ENCODING", "ffmpeg rejected recording")


def _probe_ogg(path: Path) -> bool:
    result = _run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])
    return result.returncode == 0


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False)


__all__ = ["FilesystemRecordingArchive"]
