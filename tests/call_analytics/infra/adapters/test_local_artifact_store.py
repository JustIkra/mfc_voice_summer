from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from call_analytics.infra.adapters.local_dir import LocalArtifactStore
from domain import (
    CallRecording,
    CallReport,
    ChannelLayout,
    ClientSatisfaction,
    EmotionalAssessment,
    QuestionResolution,
    RecordingId,
    Satisfaction,
)

pytestmark = pytest.mark.asyncio
MSK = timezone(timedelta(hours=3))
RID = RecordingId("call-file-store")


async def test_local_artifact_store_persists_report_json_and_pdf(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    report = CallReport(
        recording_id=RID,
        satisfaction=Satisfaction.SATISFIED,
        summary="Вопрос решён.",
        key_points=("клиент записан",),
        generated_at=datetime(2026, 6, 25, 12, 0, tzinfo=MSK),
        question_resolved=QuestionResolution(
            value="yes",
            confidence=0.9,
            evidence=("оператор подтвердил запись",),
        ),
        client_satisfaction=ClientSatisfaction(
            value="satisfied",
            score_1_5=5,
            confidence=0.8,
            evidence=("клиент поблагодарил",),
        ),
        emotional_assessment=EmotionalAssessment(
            overall="Спокойно.",
            client_emotions=("happy",),
            operator_emotions=("neutral",),
        ),
    )

    await store.save_recording(
        CallRecording(
            id=RID,
            started_at=datetime(2026, 6, 25, 11, 55, tzinfo=MSK),
            duration=timedelta(minutes=2),
            channel_layout=ChannelLayout.STEREO,
            metadata={"filename": "call-file-store.wav"},
        )
    )
    await store.save_report(report)
    await store.save_report_pdf(RID, b"%PDF-1.4")

    loaded_report = await store.load_report(RID)
    assert loaded_report is not None
    assert loaded_report.question_resolved.value == "yes"
    assert loaded_report.client_satisfaction.score_1_5 == 5
    assert await store.load_report_pdf(RID) == b"%PDF-1.4"
    assert (tmp_path / "reports" / "call-file-store.report.json").is_file()
    assert (tmp_path / "reports" / "call-file-store.pdf").is_file()
