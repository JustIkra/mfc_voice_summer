from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
    InMemoryProcessingQueue,
)
from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from call_analytics.service import CallProcessingService, ProcessingWorker
from call_analytics.service.ports import CallProcessingPipeline, RecordingWorkspace
from domain import (
    AudioBlob,
    CallProcessingJob,
    CallRecording,
    ChannelLayout,
    JobStage,
    JobStatus,
    RecordingId,
)
from tests.call_analytics.service.conftest import FakeRecordingSource

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 6, 25, 12, 0, tzinfo=MSK)
RID = RecordingId("rec-queue")


class FailingPipeline(CallProcessingPipeline):
    async def enqueue(self, recording: CallRecording) -> CallProcessingJob:
        raise AssertionError("enqueue is not used")

    async def run_next_stage(self, job_id: str) -> CallProcessingJob:
        raise AssertionError("run_next_stage is not used")

    async def process(self, recording_id: RecordingId) -> CallProcessingJob:
        raise RuntimeError("boom")

    async def retry(self, job_id: str) -> CallProcessingJob:
        raise AssertionError("retry is not used")

    async def cancel(self, job_id: str) -> CallProcessingJob:
        raise AssertionError("cancel is not used")

    async def resume(self, job_id: str) -> CallProcessingJob:
        raise AssertionError("resume is not used")


class SkippedPipeline(FailingPipeline):
    async def process(self, recording_id: RecordingId) -> CallProcessingJob:
        return (
            CallProcessingJob.create(
                recording_id.value,
                recording_id,
                NOW,
            )
            .start_stage(JobStage.TRANSCRIBE)
            .skip_empty()
        )


class ClearingWorkspace(RecordingWorkspace):
    def __init__(self) -> None:
        self.cleared: list[RecordingId] = []

    async def prepare(self, call_id, parts):
        raise AssertionError("prepare is not used")

    async def load_audio(self, call_id):
        raise AssertionError("load_audio is not used")

    async def clear(self, call_id: RecordingId) -> None:
        self.cleared.append(call_id)

    async def clear_stale(self, older_than):
        raise AssertionError("clear_stale is not used")


async def test_worker_processes_queue_message_and_acknowledges_done_job() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    artifacts = InMemoryArtifactStore()
    pipeline = CallProcessingService(
        source=FakeRecordingSource(
            {RID.value: AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)}
        ),
        transcriber=NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: NOW,
    )
    worker = ProcessingWorker(queue=queue, pipeline=pipeline, jobs=jobs)
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=1),
        channel_layout=ChannelLayout.STEREO,
    )

    await pipeline.enqueue(recording)
    await queue.publish(RID)
    processed = await worker.run_once()

    job = await jobs.get(RID.value)
    assert processed is True
    assert job is not None
    assert job.status is JobStatus.DONE
    assert queue.acked == (RID.value,)
    assert queue.rejected == ()


async def test_worker_rejects_message_when_pipeline_raises_unexpected_error() -> None:
    queue = InMemoryProcessingQueue()
    await queue.publish(RID)
    worker = ProcessingWorker(
        queue=queue,
        pipeline=FailingPipeline(),
        jobs=InMemoryJobRepository(),
        requeue_failed=False,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await worker.run_once()

    assert queue.acked == ()
    assert queue.rejected == ((RID.value, False),)


async def test_worker_clears_workspace_when_pipeline_raises_unexpected_error() -> None:
    queue = InMemoryProcessingQueue()
    workspace = ClearingWorkspace()
    await queue.publish(RID)
    worker = ProcessingWorker(
        queue=queue,
        pipeline=FailingPipeline(),
        jobs=InMemoryJobRepository(),
        requeue_failed=False,
        workspace=workspace,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await worker.run_once()

    assert workspace.cleared == [RID]


async def test_worker_recovers_running_jobs_left_by_restart() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    pipeline = CallProcessingService(
        source=FakeRecordingSource(
            {RID.value: AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)}
        ),
        transcriber=NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=InMemoryArtifactStore(),
        clock=lambda: NOW,
    )
    running = CallProcessingJob.create(RID.value, RID, NOW).start_stage(JobStage.TRANSCRIBE)
    await jobs.save(running)
    worker = ProcessingWorker(queue=queue, pipeline=pipeline, jobs=jobs)

    recovered_count = await worker.recover_interrupted_jobs()

    job = await jobs.get(RID.value)
    message = await queue.get()
    assert recovered_count == 1
    assert job is not None
    assert job.status is JobStatus.PENDING
    assert message is not None
    assert message.recording_id == RID


async def test_worker_republishes_pending_job_when_queue_is_empty() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    await jobs.save(CallProcessingJob.create(RID.value, RID, NOW))
    worker = ProcessingWorker(
        queue=queue,
        pipeline=FailingPipeline(),
        jobs=jobs,
    )

    processed = await worker.run_once()

    message = await queue.get()
    assert processed is False
    assert message is not None
    assert message.recording_id == RID


async def test_worker_does_not_republish_pending_job_again_before_reconcile_interval() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    await jobs.save(CallProcessingJob.create(RID.value, RID, NOW))
    worker = ProcessingWorker(
        queue=queue,
        pipeline=FailingPipeline(),
        jobs=jobs,
        pending_reconcile_interval_seconds=60.0,
        monotonic=lambda: 100.0,
    )

    await worker.run_once()
    assert await queue.get() is not None

    await worker.run_once()

    assert await queue.get() is None


async def test_worker_acknowledges_canceled_job_without_processing_stages() -> None:
    queue = InMemoryProcessingQueue()
    jobs = InMemoryJobRepository()
    artifacts = InMemoryArtifactStore()
    pipeline = CallProcessingService(
        source=FakeRecordingSource(
            {RID.value: AudioBlob(data=b"x", codec="wav", layout=ChannelLayout.STEREO)}
        ),
        transcriber=NoopTranscriber(RID),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=NOW),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: NOW,
    )
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=1),
        channel_layout=ChannelLayout.STEREO,
    )
    job = await pipeline.enqueue(recording)
    await pipeline.cancel(job.id)
    await queue.publish(RID)

    processed = await ProcessingWorker(queue, pipeline, jobs).run_once()

    assert processed is True
    assert queue.acked == (RID.value,)
    assert queue.rejected == ()
    assert await artifacts.load_transcript(RID) is None


async def test_worker_acknowledges_skipped_empty_job() -> None:
    queue = InMemoryProcessingQueue()
    await queue.publish(RID)
    worker = ProcessingWorker(
        queue=queue,
        pipeline=SkippedPipeline(),
        jobs=InMemoryJobRepository(),
    )

    processed = await worker.run_once()

    assert processed is True
    assert queue.acked == (RID.value,)
    assert queue.rejected == ()
