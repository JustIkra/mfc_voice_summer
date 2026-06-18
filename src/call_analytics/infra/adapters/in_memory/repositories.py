from __future__ import annotations

from collections.abc import Sequence

from call_analytics.infra.ports import ArtifactStore, JobRepository
from domain import (
    CallProcessingJob,
    CallRecording,
    CallReport,
    DiarizedTranscript,
    EmotionAnalysis,
    JobStatus,
    RecordingId,
    Transcript,
)


class InMemoryJobRepository(JobRepository):
    """Словарная реализация `JobRepository` для тестов."""

    def __init__(self) -> None:
        self._jobs: dict[str, CallProcessingJob] = {}

    async def save(self, job: CallProcessingJob) -> None:
        self._jobs[job.id] = job

    async def get(self, job_id: str) -> CallProcessingJob | None:
        return self._jobs.get(job_id)

    async def list_by_status(
        self, status: JobStatus
    ) -> Sequence[CallProcessingJob]:
        return [job for job in self._jobs.values() if job.status is status]


class InMemoryArtifactStore(ArtifactStore):
    """Словарная реализация `ArtifactStore` для тестов."""

    def __init__(self) -> None:
        self._recordings: dict[str, CallRecording] = {}
        self._transcripts: dict[str, Transcript] = {}
        self._diarizations: dict[str, DiarizedTranscript] = {}
        self._emotions: dict[str, EmotionAnalysis] = {}
        self._reports: dict[str, CallReport] = {}

    async def save_recording(self, recording: CallRecording) -> None:
        self._recordings[recording.id.value] = recording

    async def load_recording(
        self, recording_id: RecordingId
    ) -> CallRecording | None:
        return self._recordings.get(recording_id.value)

    async def save_transcript(self, transcript: Transcript) -> None:
        self._transcripts[transcript.recording_id.value] = transcript

    async def load_transcript(
        self, recording_id: RecordingId
    ) -> Transcript | None:
        return self._transcripts.get(recording_id.value)

    async def save_diarization(self, diarized: DiarizedTranscript) -> None:
        self._diarizations[diarized.recording_id.value] = diarized

    async def load_diarization(
        self, recording_id: RecordingId
    ) -> DiarizedTranscript | None:
        return self._diarizations.get(recording_id.value)

    async def save_emotion(self, emotion: EmotionAnalysis) -> None:
        self._emotions[emotion.recording_id.value] = emotion

    async def load_emotion(
        self, recording_id: RecordingId
    ) -> EmotionAnalysis | None:
        return self._emotions.get(recording_id.value)

    async def save_report(self, report: CallReport) -> None:
        self._reports[report.recording_id.value] = report

    async def load_report(self, recording_id: RecordingId) -> CallReport | None:
        return self._reports.get(recording_id.value)


__all__ = ["InMemoryArtifactStore", "InMemoryJobRepository"]
