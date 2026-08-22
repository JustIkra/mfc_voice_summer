from __future__ import annotations

from dataclasses import dataclass

from domain.diarization import DiarizedTranscript
from domain.emotion import EmotionAnalysis
from domain.recording import CallRecording
from domain.report import CallReport
from domain.transcript import Transcript


@dataclass(frozen=True, slots=True)
class FinalReportDocument:
    recording: CallRecording
    report: CallReport
    transcript: Transcript
    diarized: DiarizedTranscript
    emotions: EmotionAnalysis


__all__ = ["FinalReportDocument"]
