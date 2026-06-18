from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from domain.recording import RecordingId


class Satisfaction(Enum):
    SATISFIED = auto()
    NEUTRAL = auto()
    DISSATISFIED = auto()


@dataclass(frozen=True, slots=True)
class CallReport:
    recording_id: RecordingId
    satisfaction: Satisfaction
    summary: str
    key_points: tuple[str, ...]
    generated_at: datetime


__all__ = ["CallReport", "Satisfaction"]
