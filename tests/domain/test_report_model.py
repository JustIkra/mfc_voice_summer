from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain import (
    CallReport,
    ClientSatisfaction,
    EmotionalAssessment,
    QuestionResolution,
    RecordingId,
    Satisfaction,
)


def test_call_report_contains_required_quality_fields() -> None:
    generated_at = datetime(2026, 6, 25, 12, 0, tzinfo=timezone(timedelta(hours=3)))

    report = CallReport(
        recording_id=RecordingId("call-1"),
        satisfaction=Satisfaction.DISSATISFIED,
        summary="Клиент не получил полный ответ.",
        key_points=("нужна повторная консультация",),
        generated_at=generated_at,
        question_resolved=QuestionResolution(
            value="partial",
            confidence=0.82,
            evidence=("Оператор предложил следующий шаг, но не закрыл вопрос.",),
        ),
        client_satisfaction=ClientSatisfaction(
            value="dissatisfied",
            score_1_5=2,
            confidence=0.74,
            evidence=("Клиент несколько раз выражал раздражение.",),
        ),
        emotional_assessment=EmotionalAssessment(
            overall="Напряжённый диалог с раздражением клиента к концу звонка.",
            client_emotions=("angry",),
            operator_emotions=("neutral",),
            evidence=("SER показывает angry на реплике клиента.",),
        ),
        client_speaker="SPEAKER_01",
        operator_speaker="SPEAKER_00",
        risks=("риск повторного обращения",),
        recommendations=("перезвонить клиенту",),
    )

    assert report.client_speaker == "SPEAKER_01"
    assert report.operator_speaker == "SPEAKER_00"
    assert report.question_resolved.value == "partial"
    assert report.client_satisfaction.score_1_5 == 2
    assert report.emotional_assessment.client_emotions == ("angry",)
    assert report.risks == ("риск повторного обращения",)
