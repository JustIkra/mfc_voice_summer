from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any


@dataclass(frozen=True, slots=True)
class RecordingId:
    value: str


@dataclass(frozen=True, slots=True)
class Period:
    start: datetime
    end: datetime


class ChannelLayout(Enum):
    MONO = auto()
    STEREO = auto()


class CallerNameSource(Enum):
    CDR = "cdr"
    ACCOUNT = "account"
    TRANSCRIPT = "transcript"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class QueueIdentity:
    extension: str
    name: str


@dataclass(frozen=True, slots=True)
class CallerIdentity:
    id: str | None = None
    name: str | None = None
    name_source: CallerNameSource = CallerNameSource.UNKNOWN
    name_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    id: int
    extension: str
    name: str


@dataclass(frozen=True, slots=True)
class SourceRecordingIdentity:
    acct_id: str | None
    filenames: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DiscoveredCall:
    id: RecordingId
    started_at: datetime
    duration: timedelta
    queue: QueueIdentity
    caller: CallerIdentity
    operator: OperatorIdentity | None
    source_recording: SourceRecordingIdentity


@dataclass(frozen=True, slots=True)
class AudioBlob:
    data: bytes
    codec: str
    layout: ChannelLayout


@dataclass(frozen=True, slots=True)
class CallRecording:
    id: RecordingId
    started_at: datetime
    duration: timedelta
    channel_layout: ChannelLayout
    operator_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    queue: QueueIdentity | None = None
    caller: CallerIdentity = field(default_factory=CallerIdentity)
    operator: OperatorIdentity | None = None
    source_recording: SourceRecordingIdentity | None = None


__all__ = [
    "AudioBlob",
    "CallRecording",
    "CallerIdentity",
    "CallerNameSource",
    "ChannelLayout",
    "DiscoveredCall",
    "OperatorIdentity",
    "Period",
    "QueueIdentity",
    "RecordingId",
    "SourceRecordingIdentity",
]
