from __future__ import annotations

from abc import ABC, abstractmethod

from domain import CallReport, DiarizedTranscript, EmotionAnalysis, Transcript


class ReportRenderer(ABC):
    @abstractmethod
    async def render(
        self,
        report: CallReport,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> bytes:
        """Render the final human-readable report artifact."""


__all__ = ["ReportRenderer"]
