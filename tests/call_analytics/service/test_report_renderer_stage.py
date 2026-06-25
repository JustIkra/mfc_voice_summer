from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.in_memory import (
    InMemoryArtifactStore,
    InMemoryJobRepository,
)
from call_analytics.infra.adapters.noop import (
    NoopDiarizer,
    NoopEmotionRecognizer,
    NoopReportGenerator,
    NoopTranscriber,
)
from call_analytics.infra.ports import ReportRenderer
from call_analytics.service import CallProcessingService
from domain import (
    AudioBlob,
    CallRecording,
    CallReport,
    ChannelLayout,
    DiarizedTranscript,
    EmotionAnalysis,
    JobStatus,
    RecordingId,
    Transcript,
)
from tests.call_analytics.service.conftest import FakeRecordingSource

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 6, 25, 12, 0, tzinfo=MSK)
RID = RecordingId("report-pdf")


class FakeReportRenderer(ReportRenderer):
    async def render(
        self,
        report: CallReport,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> bytes:
        return f"%PDF-1.4\n{report.recording_id.value}".encode()


async def test_report_stage_saves_pdf_artifact_when_renderer_is_configured() -> None:
    jobs, artifacts = InMemoryJobRepository(), InMemoryArtifactStore()
    service = CallProcessingService(
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
        report_renderer=FakeReportRenderer(),
    )
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=1),
        channel_layout=ChannelLayout.STEREO,
    )

    await service.enqueue(recording)
    job = await service.process(RID)

    assert job.status is JobStatus.DONE
    assert await artifacts.load_report_pdf(RID) == b"%PDF-1.4\nreport-pdf"
