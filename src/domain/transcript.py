from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from domain.recording import RecordingId


@dataclass(frozen=True, slots=True)
class TimeSpan:
    start: timedelta
    end: timedelta

    @classmethod
    def from_seconds(cls, start: float, end: float) -> TimeSpan:
        return cls(
            start=timedelta(seconds=start),
            end=timedelta(seconds=end),
        )


@dataclass(frozen=True, slots=True)
class TranscriptWord:
    span: TimeSpan
    text: str
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    span: TimeSpan
    text: str
    channel: int | None = None
    confidence: float = 1.0
    words: tuple[TranscriptWord, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Transcript:
    recording_id: RecordingId
    language: str
    segments: tuple[TranscriptSegment, ...]
    full_text: str


__all__ = ["TimeSpan", "Transcript", "TranscriptSegment", "TranscriptWord"]
