from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from call_analytics.service.ports import ArtifactStore, CallRepository, JobRepository
from domain import (
    CallProcessingJob,
    CallRecording,
    CallReport,
    DiarizedTranscript,
    DiscoveredCall,
    EmotionAnalysis,
    JobStatus,
    RecordingId,
    Transcript,
)

_RETRYABLE_ERROR_KINDS = frozenset({"CONNECTION", "TIMEOUT", "RATE_LIMIT", "SERVER"})


class InMemoryJobRepository(JobRepository):
    """Словарная реализация `JobRepository` для тестов."""

    def __init__(self) -> None:
        self._jobs: dict[str, CallProcessingJob] = {}

    async def save(self, job: CallProcessingJob) -> None:
        self._jobs[job.id] = job

    async def get(self, job_id: str) -> CallProcessingJob | None:
        return self._jobs.get(job_id)

    async def delete(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    async def list_by_status(self, status: JobStatus) -> Sequence[CallProcessingJob]:
        return [job for job in self._jobs.values() if job.status is status]


class InMemoryCallRepository(CallRepository):
    def __init__(self) -> None:
        self._recordings: dict[str, CallRecording] = {}
        self._statuses: dict[str, JobStatus] = {}
        self._attempt_counts: dict[str, int] = {}
        self._error_kinds: dict[str, str | None] = {}

    async def contains(self, recording_id: RecordingId) -> bool:
        return recording_id.value in self._statuses

    async def register(self, recording: CallRecording, job: CallProcessingJob) -> bool:
        if await self.contains(recording.id):
            return False
        self._recordings[recording.id.value] = recording
        self._statuses[recording.id.value] = job.status
        self._attempt_counts[recording.id.value] = sum(job.attempts.values())
        self._error_kinds[recording.id.value] = None
        return True

    async def register_skipped(
        self,
        call: DiscoveredCall,
        reason: str,
        now: datetime,
    ) -> None:
        del reason, now
        self._statuses.setdefault(call.id.value, JobStatus.SKIPPED_EMPTY)
        self._attempt_counts.setdefault(call.id.value, 0)
        self._error_kinds.setdefault(call.id.value, "EMPTY_RECORDING")

    async def register_failed(
        self,
        call: DiscoveredCall,
        kind: str,
        reason: str,
        now: datetime,
    ) -> None:
        del reason, now
        self._statuses.setdefault(call.id.value, JobStatus.FAILED)
        self._attempt_counts.setdefault(call.id.value, 0)
        self._error_kinds.setdefault(call.id.value, kind)

    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None:
        return self._recordings.get(recording_id.value)

    async def status(self, recording_id: RecordingId) -> JobStatus | None:
        return self._statuses.get(recording_id.value)

    async def mark_skipped_empty(self, recording_id: RecordingId, reason: str) -> None:
        del reason
        self._statuses[recording_id.value] = JobStatus.SKIPPED_EMPTY
        self._error_kinds[recording_id.value] = "EMPTY_RECORDING"

    async def list_retryable(self, max_attempts: int) -> Sequence[CallRecording]:
        return [
            recording
            for key, recording in self._recordings.items()
            if self._statuses.get(key) is JobStatus.FAILED
            and self._attempt_counts.get(key, 0) < max_attempts
            and self._error_kinds.get(key) in _RETRYABLE_ERROR_KINDS
        ]


class InMemoryArtifactStore(ArtifactStore):
    """Словарная реализация `ArtifactStore` для тестов."""

    def __init__(self) -> None:
        self._recordings: dict[str, CallRecording] = {}
        self._transcripts: dict[str, Transcript] = {}
        self._diarizations: dict[str, DiarizedTranscript] = {}
        self._emotions: dict[str, EmotionAnalysis] = {}
        self._reports: dict[str, CallReport] = {}
        self._report_pdfs: dict[str, bytes] = {}

    async def save_recording(self, recording: CallRecording) -> None:
        self._recordings[recording.id.value] = recording

    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None:
        return self._recordings.get(recording_id.value)

    async def save_transcript(self, transcript: Transcript) -> None:
        self._transcripts[transcript.recording_id.value] = transcript

    async def load_transcript(self, recording_id: RecordingId) -> Transcript | None:
        return self._transcripts.get(recording_id.value)

    async def save_diarization(self, diarized: DiarizedTranscript) -> None:
        self._diarizations[diarized.recording_id.value] = diarized

    async def load_diarization(self, recording_id: RecordingId) -> DiarizedTranscript | None:
        return self._diarizations.get(recording_id.value)

    async def save_emotion(self, emotion: EmotionAnalysis) -> None:
        self._emotions[emotion.recording_id.value] = emotion

    async def load_emotion(self, recording_id: RecordingId) -> EmotionAnalysis | None:
        return self._emotions.get(recording_id.value)

    async def save_report(self, report: CallReport) -> None:
        self._reports[report.recording_id.value] = report

    async def load_report(self, recording_id: RecordingId) -> CallReport | None:
        return self._reports.get(recording_id.value)

    async def save_report_pdf(self, recording_id: RecordingId, content: bytes) -> None:
        self._report_pdfs[recording_id.value] = content

    async def load_report_pdf(self, recording_id: RecordingId) -> bytes | None:
        return self._report_pdfs.get(recording_id.value)

    async def delete_outputs(self, recording_id: RecordingId) -> None:
        key = recording_id.value
        self._transcripts.pop(key, None)
        self._diarizations.pop(key, None)
        self._emotions.pop(key, None)
        self._reports.pop(key, None)
        self._report_pdfs.pop(key, None)


__all__ = ["InMemoryArtifactStore", "InMemoryCallRepository", "InMemoryJobRepository"]
