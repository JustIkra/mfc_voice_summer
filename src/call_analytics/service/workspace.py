from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from call_analytics.service.ports import (
    ArtifactStore,
    CallProcessingPipeline,
    CallRecordingSource,
    JobRepository,
    ProcessingQueue,
    RecordingInbox,
)
from domain import CallProcessingJob, CallRecording, CallReport, JobStatus, Period, RecordingId

MSK = timezone(timedelta(hours=3))


class RecordingNotFound(Exception):
    def __init__(self, recording_id: RecordingId) -> None:
        super().__init__(f"recording {recording_id.value} not found")


class JobNotFound(Exception):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"job {job_id} not found")


class RecordingUploadUnavailable(Exception):
    pass


class JobInProgress(Exception):
    def __init__(self, recording_id: RecordingId) -> None:
        super().__init__(f"recording {recording_id.value} is in progress")


@dataclass(frozen=True, slots=True)
class RecordingWorkspaceItem:
    recording: CallRecording
    job: CallProcessingJob | None


class PipelineWorkspace:
    def __init__(
        self,
        source: CallRecordingSource,
        jobs: JobRepository,
        artifacts: ArtifactStore,
        queue: ProcessingQueue,
        pipeline: CallProcessingPipeline,
        clock: Callable[[], datetime],
        inbox: RecordingInbox | None = None,
    ) -> None:
        self._source = source
        self._jobs = jobs
        self._artifacts = artifacts
        self._queue = queue
        self._pipeline = pipeline
        self._clock = clock
        self._inbox = inbox

    async def list_recordings(
        self,
        period: Period | None = None,
    ) -> Sequence[RecordingWorkspaceItem]:
        recordings = await self._source.list_recordings(period or self._all_recordings_period())
        return [
            RecordingWorkspaceItem(
                recording=recording,
                job=await self._jobs.get(recording.id.value),
            )
            for recording in recordings
        ]

    async def enqueue_recording(self, recording_id: RecordingId) -> CallProcessingJob:
        recording = await self._find_recording(recording_id)
        existing = await self._jobs.get(recording_id.value)
        job = existing or await self._pipeline.enqueue(recording)
        await self._queue.publish(recording_id)
        return job

    async def upload_recording(
        self,
        filename: str,
        content: bytes,
    ) -> RecordingWorkspaceItem:
        if self._inbox is None:
            raise RecordingUploadUnavailable
        recording = await self._inbox.save_wav(filename, content)
        return RecordingWorkspaceItem(
            recording=recording,
            job=await self._jobs.get(recording.id.value),
        )

    async def get_job(self, job_id: str) -> CallProcessingJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    async def process_recording(self, recording_id: RecordingId) -> CallProcessingJob:
        return await self._pipeline.process(recording_id)

    async def retry_job(self, job_id: str) -> CallProcessingJob:
        try:
            job = await self._pipeline.retry(job_id)
        except KeyError as error:
            raise JobNotFound(job_id) from error
        await self._queue.publish(job.recording_id)
        return job

    async def delete_recording_report(self, recording_id: RecordingId) -> RecordingWorkspaceItem:
        recording = await self._find_recording(recording_id)
        await self._ensure_can_replace(recording_id)
        await self._jobs.delete(recording_id.value)
        await self._artifacts.delete_outputs(recording_id)
        return RecordingWorkspaceItem(recording=recording, job=None)

    async def overwrite_recording_report(self, recording_id: RecordingId) -> CallProcessingJob:
        await self.delete_recording_report(recording_id)
        return await self.enqueue_recording(recording_id)

    async def load_report(self, recording_id: RecordingId) -> CallReport | None:
        return await self._artifacts.load_report(recording_id)

    async def load_report_pdf(self, recording_id: RecordingId) -> bytes | None:
        return await self._artifacts.load_report_pdf(recording_id)

    async def _find_recording(self, recording_id: RecordingId) -> CallRecording:
        items = await self.list_recordings()
        for item in items:
            if item.recording.id == recording_id:
                return item.recording
        raise RecordingNotFound(recording_id)

    async def _ensure_can_replace(self, recording_id: RecordingId) -> None:
        job = await self._jobs.get(recording_id.value)
        if job is not None and job.status in {JobStatus.PENDING, JobStatus.RUNNING}:
            raise JobInProgress(recording_id)

    def _all_recordings_period(self) -> Period:
        return Period(
            start=datetime(1970, 1, 1, tzinfo=MSK),
            end=self._clock() + timedelta(days=1),
        )


__all__ = [
    "JobInProgress",
    "JobNotFound",
    "PipelineWorkspace",
    "RecordingNotFound",
    "RecordingUploadUnavailable",
    "RecordingWorkspaceItem",
]
