from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from call_analytics.service.ports import (
    ArtifactStore,
    CallListItem,
    CallPage,
    CallPageRequest,
    CallRepository,
    DashboardFilter,
    DashboardRepository,
    DashboardSummary,
    FinalReportRepository,
    JobRepository,
    OperatorSummary,
    SyncRunRepository,
    SyncStatus,
)
from domain import (
    CallProcessingJob,
    CallRecording,
    CallReport,
    DiarizedTranscript,
    DiscoveredCall,
    EmotionAnalysis,
    FinalReportDocument,
    JobStatus,
    Period,
    RecordingId,
    Transcript,
    build_report_payload,
)

_RETRYABLE_ERROR_KINDS = frozenset(
    {
        "ARCHIVE_CAPACITY",
        "ARCHIVE_ENCODING",
        "ARCHIVE_IO",
        "CONNECTION",
        "RATE_LIMIT",
        "SERVER",
        "TIMEOUT",
    }
)


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

    async def list_stale_running(self, older_than: datetime) -> Sequence[CallProcessingJob]:
        return [
            job
            for job in self._jobs.values()
            if job.status is JobStatus.RUNNING and job.created_at < older_than
        ]


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
        self._error_kinds[recording.id.value] = job.last_error[0] if job.last_error else None
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


class InMemoryFinalReportRepository(FinalReportRepository):
    def __init__(self, jobs: JobRepository | None = None) -> None:
        self._payloads: dict[str, dict[str, object]] = {}
        self._jobs = jobs

    async def finalize(self, job: CallProcessingJob, document: FinalReportDocument) -> None:
        if job.recording_id != document.recording.id:
            raise ValueError("job and final report have different recording ids")
        self._payloads[job.recording_id.value] = build_report_payload(document)
        if self._jobs is not None:
            await self._jobs.save(job)

    async def load_payload(self, recording_id: RecordingId) -> dict[str, object] | None:
        return self._payloads.get(recording_id.value)


class InMemoryDashboardRepository(DashboardRepository):
    def __init__(
        self,
        summary: DashboardSummary | None = None,
        operators: Sequence[OperatorSummary] = (),
        calls: Sequence[CallListItem] = (),
        processing: Mapping[str, int] | None = None,
    ) -> None:
        self._summary = summary or DashboardSummary(
            total_calls=0,
            resolved_calls=0,
            average_duration_seconds=0.0,
            attention_calls=0,
            satisfaction={"satisfied": 0, "neutral": 0, "dissatisfied": 0},
        )
        self._operators = list(operators)
        self._calls = list(calls)
        self._processing = dict(processing or {})

    async def summary(self, filters: DashboardFilter) -> DashboardSummary:
        del filters
        return self._summary

    async def operators(self, filters: DashboardFilter) -> Sequence[OperatorSummary]:
        del filters
        return self._operators

    async def list_calls(self, request: CallPageRequest) -> CallPage:
        start = (request.page - 1) * request.page_size
        end = start + request.page_size
        return CallPage(
            items=self._calls[start:end],
            page=request.page,
            page_size=request.page_size,
            total_items=len(self._calls),
        )

    async def processing_counts(self) -> Mapping[str, int]:
        return self._processing


class InMemorySyncRunRepository(SyncRunRepository):
    def __init__(self) -> None:
        self._last: SyncStatus | None = None
        self._running_id: int | None = None
        self._next_id = 1

    async def start(self, period: Period, started_at: datetime) -> int | None:
        if self._running_id is not None:
            return None
        run_id = self._next_id
        self._next_id += 1
        self._running_id = run_id
        self._last = SyncStatus(
            window_start=period.start,
            window_end=period.end,
            status="running",
            started_at=started_at,
            finished_at=None,
            discovered=0,
            queued=0,
            skipped=0,
            failed=0,
        )
        return run_id

    async def finish(
        self,
        run_id: int,
        finished_at: datetime,
        status: str,
        discovered: int,
        queued: int,
        skipped: int,
        failed: int,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if run_id != self._running_id or self._last is None:
            raise KeyError(f"sync run {run_id} not found")
        self._last = SyncStatus(
            window_start=self._last.window_start,
            window_end=self._last.window_end,
            status=status,
            started_at=self._last.started_at,
            finished_at=finished_at,
            discovered=discovered,
            queued=queued,
            skipped=skipped,
            failed=failed,
            error_kind=error_kind,
            error_message=error_message,
        )
        self._running_id = None

    async def last(self) -> SyncStatus | None:
        return self._last


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


__all__ = [
    "InMemoryArtifactStore",
    "InMemoryCallRepository",
    "InMemoryDashboardRepository",
    "InMemoryFinalReportRepository",
    "InMemoryJobRepository",
    "InMemorySyncRunRepository",
]
