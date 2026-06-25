from __future__ import annotations

from abc import ABC, abstractmethod

from domain import (
    CallRecording,
    CallReport,
    DiarizedTranscript,
    EmotionAnalysis,
    RecordingId,
    Transcript,
)


class ArtifactStore(ABC):
    """Абстрактный порт хранения выходов стадий пайплайна.

    Персист промежуточных артефактов делает ретрай идемпотентным:
    упавшая поздняя стадия не пересчитывает дорогой whisper.
    """

    @abstractmethod
    async def save_recording(self, recording: CallRecording) -> None: ...

    @abstractmethod
    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None: ...

    @abstractmethod
    async def save_transcript(self, transcript: Transcript) -> None: ...

    @abstractmethod
    async def load_transcript(self, recording_id: RecordingId) -> Transcript | None: ...

    @abstractmethod
    async def save_diarization(self, diarized: DiarizedTranscript) -> None: ...

    @abstractmethod
    async def load_diarization(
        self, recording_id: RecordingId
    ) -> DiarizedTranscript | None: ...

    @abstractmethod
    async def save_emotion(self, emotion: EmotionAnalysis) -> None: ...

    @abstractmethod
    async def load_emotion(self, recording_id: RecordingId) -> EmotionAnalysis | None: ...

    @abstractmethod
    async def save_report(self, report: CallReport) -> None: ...

    @abstractmethod
    async def load_report(self, recording_id: RecordingId) -> CallReport | None: ...

    @abstractmethod
    async def save_report_pdf(self, recording_id: RecordingId, content: bytes) -> None: ...

    @abstractmethod
    async def load_report_pdf(self, recording_id: RecordingId) -> bytes | None: ...


__all__ = ["ArtifactStore"]
