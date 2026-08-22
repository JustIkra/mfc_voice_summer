from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from domain import AudioBlob, ChannelLayout, DiscoveredCall, Period, RecordingId


@dataclass(frozen=True, slots=True)
class TelephonyAccount:
    id: int
    extension: str
    fullname: str


@dataclass(frozen=True, slots=True)
class PreparedAudio:
    duration: timedelta
    layout: ChannelLayout
    codec: str


class InvalidRecordingError(ValueError):
    pass


class TelephonyGateway(ABC):
    @abstractmethod
    async def list_accounts(self) -> Sequence[TelephonyAccount]:
        raise NotImplementedError

    @abstractmethod
    async def list_calls(
        self,
        period: Period,
        accounts: Sequence[TelephonyAccount],
    ) -> Sequence[DiscoveredCall]:
        raise NotImplementedError

    @abstractmethod
    async def recording_files(self, acct_id: str) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    async def download_recording(self, filename: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class RecordingWorkspace(ABC):
    @abstractmethod
    async def prepare(self, call_id: RecordingId, parts: Sequence[bytes]) -> PreparedAudio:
        raise NotImplementedError

    @abstractmethod
    async def load_audio(self, call_id: RecordingId) -> AudioBlob:
        raise NotImplementedError

    @abstractmethod
    async def clear(self, call_id: RecordingId) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear_stale(self, older_than: datetime) -> int:
        raise NotImplementedError


__all__ = [
    "InvalidRecordingError",
    "PreparedAudio",
    "RecordingWorkspace",
    "TelephonyAccount",
    "TelephonyGateway",
]
