from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

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
from call_analytics.service.workspace import PipelineWorkspace
from call_analytics.web import create_app
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
        raise AssertionError("ack is not used by web tests")

    async def reject(self, message: ProcessingMessage, requeue: bool) -> None:
        raise AssertionError("reject is not used by web tests")


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

    async def save_wav(self, filename: str, content: bytes) -> CallRecording:
        recording = CallRecording(
            id=RecordingId(filename.removesuffix(".wav")),
            started_at=self._now,
            duration=timedelta(seconds=7),
            channel_layout=ChannelLayout.MONO,
            metadata={"filename": filename},
        )
        self._source.add(recording, AudioBlob(data=content, codec="wav", layout=ChannelLayout.MONO))
        return recording


def build_client() -> tuple[TestClient, MemoryQueue, InMemoryArtifactStore]:
    now = datetime(2026, 6, 25, 8, 30, tzinfo=MSK)
    recording_id = RecordingId("call-001")
    recording = CallRecording(
        id=recording_id,
        started_at=now,
        duration=timedelta(seconds=91),
        channel_layout=ChannelLayout.STEREO,
        metadata={"filename": "call-001.wav"},
    )
    source = PeriodAwareRecordingSource()
    source.add(recording, AudioBlob(data=b"demo", codec="wav", layout=ChannelLayout.STEREO))
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
    workspace = PipelineWorkspace(
        source=source,
        jobs=jobs,
        artifacts=artifacts,
        queue=queue,
        pipeline=pipeline,
        inbox=inbox,
        clock=lambda: now,
    )
    return TestClient(create_app(lambda: workspace)), queue, artifacts


def test_recordings_endpoint_lists_available_recordings() -> None:
    client, _, _ = build_client()

    response = client.get("/api/recordings")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "call-001",
            "filename": "call-001.wav",
            "started_at": "2026-06-25T08:30:00+03:00",
            "duration_seconds": 91.0,
            "channel_layout": "STEREO",
            "job": None,
        }
    ]


def test_upload_endpoint_saves_wav_and_returns_recording() -> None:
    client, queue, _ = build_client()

    response = client.post(
        "/api/recordings",
        files={"file": ("uploaded.wav", b"RIFFdemo", "audio/wav")},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "uploaded"
    assert response.json()["filename"] == "uploaded.wav"
    assert response.json()["job"]["status"] == "pending"
    assert [item.value for item in queue.published] == ["uploaded"]


def test_enqueue_endpoint_creates_job_and_publishes_message() -> None:
    client, queue, _ = build_client()

    response = client.post("/api/recordings/call-001/jobs")

    assert response.status_code == 201
    assert response.json()["id"] == "call-001"
    assert response.json()["status"] == "pending"
    assert [item.value for item in queue.published] == ["call-001"]


def test_process_endpoint_is_not_exposed_from_web_api() -> None:
    client, _, _ = build_client()
    client.post("/api/recordings/call-001/jobs")

    response = client.post("/api/jobs/call-001/process")

    assert response.status_code == 404


def test_job_events_websocket_streams_current_status() -> None:
    client, _, _ = build_client()
    client.post("/api/recordings/call-001/jobs")

    with client.websocket_connect("/api/jobs/call-001/events") as websocket:
        message = websocket.receive_json()

    assert message["id"] == "call-001"
    assert message["status"] == "pending"
    assert message["completed_stages"] == []


def test_report_pdf_endpoint_returns_saved_artifact() -> None:
    client, _, artifacts = build_client()
    client.post("/api/recordings/call-001/jobs")
    client.post("/api/jobs/call-001/process")
    asyncio.run(artifacts.save_report_pdf(RecordingId("call-001"), b"%PDF-1.4 demo"))

    response = client.get("/api/jobs/call-001/report.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 demo"
