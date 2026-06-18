from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto

from domain.diarization import SpeakerRole
from domain.recording import RecordingId
from domain.transcript import TimeSpan


class EmotionLabel(Enum):
    NEUTRAL = auto()
    HAPPY = auto()
    ANGRY = auto()
    SAD = auto()
    FEARFUL = auto()
    DISGUSTED = auto()
    SURPRISED = auto()


@dataclass(frozen=True, slots=True)
class SegmentEmotion:
    span: TimeSpan
    role: SpeakerRole
    label: EmotionLabel
    scores: Mapping[EmotionLabel, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmotionAnalysis:
    recording_id: RecordingId
    segments: tuple[SegmentEmotion, ...]


__all__ = ["EmotionAnalysis", "EmotionLabel", "SegmentEmotion"]
