from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from call_analytics.service.dashboard import (
    CallPageRequest,
    DashboardFilter,
    DashboardSummary,
)
from call_analytics.service.ports import (
    ArtifactStore,
    CallRepository,
    DashboardRepository,
    FinalReportRepository,
    RecordingWorkspace,
    SyncRunRepository,
    TelephonyGateway,
)
from domain import (
    CallRecording,
    CallReport,
    ChannelLayout,
    DiarizedTranscript,
    EmotionAnalysis,
    FinalReportDocument,
    RecordingId,
    Satisfaction,
    Transcript,
)

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=MSK)
RID = RecordingId("cdr:call-42")


def test_final_report_document_keeps_every_final_input() -> None:
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(seconds=91),
        channel_layout=ChannelLayout.MONO,
    )
    report = CallReport(
        recording_id=RID,
        satisfaction=Satisfaction.NEUTRAL,
        summary="summary",
        key_points=(),
        generated_at=NOW,
    )
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(),
        full_text="текст",
    )
    diarized = DiarizedTranscript(recording_id=RID, segments=())
    emotions = EmotionAnalysis(recording_id=RID, segments=())

    document = FinalReportDocument(
        recording=recording,
        report=report,
        transcript=transcript,
        diarized=diarized,
        emotions=emotions,
    )

    assert document.recording.id == document.report.recording_id
    assert document.transcript.full_text == "текст"


def test_new_ports_are_abstract_boundaries() -> None:
    for port in (
        CallRepository,
        FinalReportRepository,
        SyncRunRepository,
        DashboardRepository,
        TelephonyGateway,
        RecordingWorkspace,
    ):
        assert inspect.isabstract(port)


def test_pipeline_artifact_store_has_only_transient_contract() -> None:
    assert {
        "delete_outputs",
        "load_diarization",
        "load_emotion",
        "load_recording",
        "load_transcript",
        "save_diarization",
        "save_emotion",
        "save_recording",
        "save_transcript",
    } <= ArtifactStore.__abstractmethods__


def test_dashboard_request_and_summary_shapes_are_stable() -> None:
    filters = DashboardFilter(date_from=NOW - timedelta(days=30), date_to=NOW)
    request = CallPageRequest(filters=filters)
    summary = DashboardSummary(
        total_calls=2,
        resolved_calls=1,
        average_duration_seconds=91.5,
        attention_calls=1,
        satisfaction={"satisfied": 1, "neutral": 1, "dissatisfied": 0},
    )

    assert request.page == 1
    assert request.page_size == 50
    assert summary.satisfaction["satisfied"] == 1
