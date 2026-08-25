from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from domain import AudioBlob, RecordingId

ArchiveState = Literal["ok", "warning", "critical", "full"]
ArchiveErrorKind = Literal["ARCHIVE_CAPACITY", "ARCHIVE_ENCODING", "ARCHIVE_IO"]


class RecordingArchiveError(RuntimeError):
    def __init__(self, kind: ArchiveErrorKind, message: str) -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ArchivedRecording:
    recording_id: RecordingId
    mime_type: str
    codec: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ArchivedRecordingFile:
    path: Path
    mime_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class RecordingStorageStatus:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: int
    state: ArchiveState

    @classmethod
    def from_usage(
        cls,
        total_bytes: int,
        used_bytes: int,
        free_bytes: int,
        reserve_bytes: int,
    ) -> RecordingStorageStatus:
        free_percent = 100.0 * free_bytes / total_bytes if total_bytes > 0 else 0.0
        used_percent = round(100.0 * used_bytes / total_bytes) if total_bytes > 0 else 0
        if free_bytes < reserve_bytes:
            state: ArchiveState = "full"
        elif free_percent <= 10.0:
            state = "critical"
        elif free_percent <= 20.0:
            state = "warning"
        else:
            state = "ok"
        return cls(total_bytes, used_bytes, free_bytes, used_percent, state)


class RecordingArchive(ABC):
    @abstractmethod
    async def store(
        self,
        recording_id: RecordingId,
        audio: AudioBlob,
    ) -> ArchivedRecording:
        raise NotImplementedError

    @abstractmethod
    async def locate(self, recording_id: RecordingId) -> ArchivedRecordingFile | None:
        raise NotImplementedError

    @abstractmethod
    async def storage_status(self) -> RecordingStorageStatus:
        raise NotImplementedError


__all__ = [
    "ArchiveErrorKind",
    "ArchiveState",
    "ArchivedRecording",
    "ArchivedRecordingFile",
    "RecordingArchive",
    "RecordingArchiveError",
    "RecordingStorageStatus",
]
