from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from domain.recording import RecordingId


@dataclass(frozen=True, slots=True)
class TimeSpan:
    start: timedelta
    end: timedelta


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    span: TimeSpan
    text: str
    channel: int | None = None
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class Transcript:
    recording_id: RecordingId
    language: str
    segments: tuple[TranscriptSegment, ...]
    full_text: str


__all__ = ["TimeSpan", "Transcript", "TranscriptSegment"]
