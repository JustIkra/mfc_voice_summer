from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from domain.recording import RecordingId
from domain.transcript import TimeSpan


class SpeakerRole(Enum):
    OPERATOR = auto()
    CLIENT = auto()
    UNKNOWN = auto()


@dataclass(frozen=True, slots=True)
class DiarizedSegment:
    span: TimeSpan
    role: SpeakerRole
    text: str
    speaker: str | None = None
    speaker_overlap_seconds: float = 0.0
    speaker_coverage: float = 0.0


@dataclass(frozen=True, slots=True)
class DiarizedTranscript:
    recording_id: RecordingId
    segments: tuple[DiarizedSegment, ...]


__all__ = ["DiarizedSegment", "DiarizedTranscript", "SpeakerRole"]
