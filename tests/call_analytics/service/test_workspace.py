from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
    InMemoryRecordingSource,
)
from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from call_analytics.service import CallProcessingService
from call_analytics.service.ports import ProcessingMessage, ProcessingQueue
from call_analytics.service.ports.application import RecordingInbox
from call_analytics.service.workspace import PipelineWorkspace, RecordingNotFound
from domain import AudioBlob, CallRecording, ChannelLayout, Period, RecordingId

MSK = timezone(timedelta(hours=3))


class MemoryQueue(ProcessingQueue):
    def __init__(self) -> None:
        self.published: list[RecordingId] = []

    async def publish(self, recording_id: RecordingId) -> None:
        self.published.append(recording_id)

    async def get(self) -> ProcessingMessage | None:
        return None

    async def ack(self, message: ProcessingMessage) -> None:
        raise AssertionError("ack is not used")

    async def reject(self, message: ProcessingMessage, requeue: bool) -> None:
        raise AssertionError("reject is not used")


class PeriodAwareRecordingSource(InMemoryRecordingSource):
    async def list_recordings(self, period: Period) -> Sequence[CallRecording]:
        return [
            recording
            for recording in await super().list_recordings(period)
            if period.start <= recording.started_at <= period.end
        ]


class MemoryInbox(RecordingInbox):
    def __init__(self, source: InMemoryRecordingSource, now: datetime) -> None:
        self._source = source
        self._now = now
        self.saved: list[tuple[str, bytes]] = []

    async def save_wav(self, filename: str, content: bytes) -> CallRecording:
        self.saved.append((filename, content))
        recording = CallRecording(
            id=RecordingId(filename.removesuffix(".wav")),
            started_at=self._now,
            duration=timedelta(seconds=7),
            channel_layout=ChannelLayout.MONO,
            metadata={"filename": filename},
        )
        self._source.add(recording, AudioBlob(data=content, codec="wav", layout=ChannelLayout.MONO))
        return recording


def build_workspace() -> tuple[PipelineWorkspace, MemoryQueue, InMemoryArtifactStore]:
    now = datetime(2026, 6, 25, 8, 30, tzinfo=MSK)
    recording_id = RecordingId("call-001")
    source = PeriodAwareRecordingSource()
    source.add(
        CallRecording(
            id=recording_id,
            started_at=now,
            duration=timedelta(seconds=91),
            channel_layout=ChannelLayout.STEREO,
            metadata={"filename": "call-001.wav"},
        ),
        AudioBlob(data=b"demo", codec="wav", layout=ChannelLayout.STEREO),
    )
    artifacts = InMemoryArtifactStore()
    jobs = InMemoryJobRepository()
    queue = MemoryQueue()
    inbox = MemoryInbox(source, now)
    pipeline = CallProcessingService(
        source=source,
        transcriber=NoopTranscriber(recording_id),
        diarizer=NoopDiarizer(),
        emotion_recognizer=NoopEmotionRecognizer(),
        report_generator=NoopReportGenerator(generated_at=now),
        jobs=jobs,
        artifacts=artifacts,
        clock=lambda: now,
    )
    return (
        PipelineWorkspace(
            source=source,
            jobs=jobs,
            artifacts=artifacts,
            queue=queue,
            inbox=inbox,
            pipeline=pipeline,
            clock=lambda: now,
        ),
        queue,
        artifacts,
    )


async def test_list_recordings_returns_job_status_when_job_exists() -> None:
    workspace, _, _ = build_workspace()
    await workspace.enqueue_recording(RecordingId("call-001"))

    recordings = await workspace.list_recordings()

    assert len(recordings) == 1
    assert recordings[0].recording.id.value == "call-001"
    assert recordings[0].job is not None
    assert recordings[0].job.status.value == "pending"


async def test_enqueue_recording_creates_job_and_publishes_message() -> None:
    workspace, queue, _ = build_workspace()

    job = await workspace.enqueue_recording(RecordingId("call-001"))

    assert job.id == "call-001"
    assert job.status.value == "pending"
    assert [item.value for item in queue.published] == ["call-001"]


async def test_enqueue_recording_rejects_unknown_recording() -> None:
    workspace, _, _ = build_workspace()

    with pytest.raises(RecordingNotFound):
        await workspace.enqueue_recording(RecordingId("missing"))


async def test_upload_recording_saves_wav_through_inbox() -> None:
    workspace, _, _ = build_workspace()

    item = await workspace.upload_recording("new-call.wav", b"RIFFdemo")

    assert item.recording.id.value == "new-call"
    assert item.recording.metadata["filename"] == "new-call.wav"
    assert item.job is None


async def test_process_recording_runs_pipeline_to_report() -> None:
    workspace, _, _ = build_workspace()
    await workspace.enqueue_recording(RecordingId("call-001"))

    job = await workspace.process_recording(RecordingId("call-001"))
    report = await workspace.load_report(RecordingId("call-001"))

    assert job.status.value == "done"
    assert report.summary


def test_report_pdf_returns_bytes_from_artifact_store() -> None:
    workspace, _, artifacts = build_workspace()
    asyncio.run(artifacts.save_report_pdf(RecordingId("call-001"), b"%PDF-1.4 demo"))

    content = asyncio.run(workspace.load_report_pdf(RecordingId("call-001")))

    assert content == b"%PDF-1.4 demo"
