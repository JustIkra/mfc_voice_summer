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
from call_analytics.infra.adapters.reporting import ReportLabReportRenderer
from call_analytics.infra.ports import ReportRenderer, ReportRendererError
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
    Satisfaction,
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


class FailingReportRenderer(ReportRenderer):
    async def render(
        self,
        report: CallReport,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> bytes:
        raise ReportRendererError.unexpected("pdf renderer unavailable")


class BuggyReportRenderer(ReportRenderer):
    async def render(
        self,
        report: CallReport,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> bytes:
        raise AssertionError("bug in renderer")


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


async def test_report_renderer_failure_marks_job_failed_without_leaving_running() -> None:
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
        report_renderer=FailingReportRenderer(),
    )
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=1),
        channel_layout=ChannelLayout.STEREO,
    )

    await service.enqueue(recording)
    job = await service.process(RID)

    saved = await jobs.get(RID.value)
    assert job.status is JobStatus.FAILED
    assert saved is not None
    assert saved.status is JobStatus.FAILED
    assert saved.last_error is not None
    assert saved.last_error[0] == "UNEXPECTED"


async def test_report_renderer_programming_error_is_not_recorded_as_stage_failure() -> None:
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
        report_renderer=BuggyReportRenderer(),
    )
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(minutes=1),
        channel_layout=ChannelLayout.STEREO,
    )

    await service.enqueue(recording)
    with pytest.raises(AssertionError, match="bug in renderer"):
        await service.process(RID)


async def test_reportlab_renderer_maps_missing_dependency_to_port_error(monkeypatch) -> None:
    renderer = ReportLabReportRenderer()

    def missing_import(name, *args, **kwargs):
        if name.startswith("reportlab"):
            raise ModuleNotFoundError("reportlab")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", missing_import)

    with pytest.raises(ReportRendererError) as error:
        await renderer.render(
            CallReport(
                recording_id=RID,
                satisfaction=Satisfaction.NEUTRAL,
                summary="summary",
                key_points=(),
                generated_at=NOW,
            ),
            Transcript(recording_id=RID, language="ru", segments=(), full_text=""),
            DiarizedTranscript(recording_id=RID, segments=()),
            EmotionAnalysis(recording_id=RID, segments=()),
        )

    assert error.value.kind is ReportRendererError.Kind.UNEXPECTED
