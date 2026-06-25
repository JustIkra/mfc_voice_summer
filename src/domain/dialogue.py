from __future__ import annotations

from dataclasses import dataclass, field

from domain.emotion import EmotionLabel
from domain.recording import RecordingId
from domain.transcript import TimeSpan


@dataclass(frozen=True, slots=True)
class EmotionEpisode:
    span: TimeSpan
    speaker: str | None
    label: EmotionLabel
    score: float
    overlap_seconds: float
    distribution: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DialogueUtterance:
    span: TimeSpan
    speaker: str | None
    text: str
    speaker_overlap_seconds: float
    speaker_coverage: float
    word_count: int
    mean_word_confidence: float | None
    emotion_episodes: tuple[EmotionEpisode, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DialogueQuality:
    utterances: int
    unknown_speaker_utterances: int
    low_speaker_coverage_utterances: int
    utterances_without_emotion: int


@dataclass(frozen=True, slots=True)
class SynchronizedDialogue:
    recording_id: RecordingId
    utterances: tuple[DialogueUtterance, ...]
    quality: DialogueQuality


__all__ = [
    "DialogueQuality",
    "DialogueUtterance",
    "EmotionEpisode",
    "SynchronizedDialogue",
]
