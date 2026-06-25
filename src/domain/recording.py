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


__all__ = ["AudioBlob", "CallRecording", "ChannelLayout", "Period", "RecordingId"]
