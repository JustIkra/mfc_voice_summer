from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from domain.recording import RecordingId


class Satisfaction(Enum):
    SATISFIED = auto()
    NEUTRAL = auto()
    DISSATISFIED = auto()


@dataclass(frozen=True, slots=True)
class QuestionResolution:
    value: str
    confidence: float
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ClientSatisfaction:
    value: str
    score_1_5: int
    confidence: float
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class EmotionalAssessment:
    overall: str
    client_emotions: tuple[str, ...] = field(default_factory=tuple)
    operator_emotions: tuple[str, ...] = field(default_factory=tuple)
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CallReport:
    recording_id: RecordingId
    satisfaction: Satisfaction
    summary: str
    key_points: tuple[str, ...]
    generated_at: datetime
    client_speaker: str = "unknown"
    operator_speaker: str = "unknown"
    question_resolved: QuestionResolution = field(
        default_factory=lambda: QuestionResolution(
            value="unknown",
            confidence=0.0,
        )
    )
    client_satisfaction: ClientSatisfaction = field(
        default_factory=lambda: ClientSatisfaction(
            value="unknown",
            score_1_5=0,
            confidence=0.0,
        )
    )
    emotional_assessment: EmotionalAssessment = field(
        default_factory=lambda: EmotionalAssessment(overall="unknown")
    )
    risks: tuple[str, ...] = field(default_factory=tuple)
    recommendations: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "CallReport",
    "ClientSatisfaction",
    "EmotionalAssessment",
    "QuestionResolution",
    "Satisfaction",
]
