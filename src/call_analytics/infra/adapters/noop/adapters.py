from __future__ import annotations

from datetime import datetime, timedelta

from call_analytics.service.ports import (
    EmotionRecognizer,
    ReportGenerator,
    SpeakerDiarizer,
    Transcriber,
)
from domain import (
    AudioBlob,
    CallReport,
    DiarizedSegment,
    DiarizedTranscript,
    EmotionAnalysis,
    EmotionLabel,
    RecordingId,
    Satisfaction,
    SegmentEmotion,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
)

_CHANNEL_ROLE = {0: SpeakerRole.OPERATOR, 1: SpeakerRole.CLIENT}


class NoopTranscriber(Transcriber):
    """Детерминированная заглушка распознавания для тестов."""

    def __init__(self, recording_id: RecordingId) -> None:
        self._recording_id = recording_id

    async def transcribe(self, recording_id: RecordingId, audio: AudioBlob) -> Transcript:
        segment = TranscriptSegment(
            span=TimeSpan(start=timedelta(0), end=timedelta(seconds=1)),
            text="noop",
            channel=0,
            confidence=1.0,
        )
        return Transcript(
            recording_id=self._recording_id,
            language="ru",
            segments=(segment,),
            full_text="noop",
        )


class NoopDiarizer(SpeakerDiarizer):
    """Заглушка: роль по номеру стерео-канала, иначе UNKNOWN."""

    async def diarize(
        self, audio: AudioBlob, transcript: Transcript
    ) -> DiarizedTranscript:
        segments = tuple(
            DiarizedSegment(
                span=seg.span,
                role=_CHANNEL_ROLE.get(seg.channel, SpeakerRole.UNKNOWN)
                if seg.channel is not None
                else SpeakerRole.UNKNOWN,
                text=seg.text,
            )
            for seg in transcript.segments
        )
        return DiarizedTranscript(
            recording_id=transcript.recording_id, segments=segments
        )


class NoopEmotionRecognizer(EmotionRecognizer):
    """Заглушка: всем сегментам NEUTRAL."""

    async def recognize(
        self, audio: AudioBlob, diarized: DiarizedTranscript
    ) -> EmotionAnalysis:
        segments = tuple(
            SegmentEmotion(
                span=seg.span,
                role=seg.role,
                label=EmotionLabel.NEUTRAL,
                scores={EmotionLabel.NEUTRAL: 1.0},
            )
            for seg in diarized.segments
        )
        return EmotionAnalysis(
            recording_id=diarized.recording_id, segments=segments
        )


class NoopReportGenerator(ReportGenerator):
    """Заглушка отчёта с фиксированным таймстампом."""

    def __init__(self, generated_at: datetime) -> None:
        self._generated_at = generated_at

    async def generate(
        self,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> CallReport:
        return CallReport(
            recording_id=diarized.recording_id,
            satisfaction=Satisfaction.NEUTRAL,
            summary="noop summary",
            key_points=(),
            generated_at=self._generated_at,
        )


__all__ = [
    "NoopDiarizer",
    "NoopEmotionRecognizer",
    "NoopReportGenerator",
    "NoopTranscriber",
]
