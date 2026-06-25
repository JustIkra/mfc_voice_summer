from __future__ import annotations

from datetime import datetime, timedelta, timezone

from call_analytics.report_view import (
    report_summary_rows,
    report_to_public_json,
    transcript_rows,
    voice_source_rows,
)
from domain import (
    CallReport,
    ClientSatisfaction,
    DiarizedSegment,
    DiarizedTranscript,
    EmotionalAssessment,
    QuestionResolution,
    RecordingId,
    Satisfaction,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
)

MSK = timezone(timedelta(hours=3))


def test_report_summary_rows_localize_states_and_hide_score() -> None:
    report = _report()

    rows = report_summary_rows(report)

    assert rows == [
        ("Решён ли вопрос", "частично"),
        ("Уверенность", "80%"),
        ("Удовлетворённость клиента", "нейтральная"),
    ]


def test_public_report_json_uses_russian_states_and_percent_confidence() -> None:
    payload = report_to_public_json(_report())

    assert payload["satisfaction"] == "нейтральная"
    assert payload["question_resolved"]["value"] == "частично"
    assert payload["question_resolved"]["confidence"] == "80%"
    assert payload["client_satisfaction"]["value"] == "нейтральная"
    assert payload["client_satisfaction"]["confidence"] == "63%"
    assert "score_1_5" not in payload["client_satisfaction"]


def test_voice_source_rows_label_client_and_operator_sources() -> None:
    rows = voice_source_rows(
        _report(),
        DiarizedTranscript(
            recording_id=RecordingId("call-ru"),
            segments=(
                DiarizedSegment(
                    span=TimeSpan(timedelta(seconds=0), timedelta(seconds=1)),
                    role=SpeakerRole.UNKNOWN,
                    text="",
                    speaker="SPEAKER_00",
                ),
                DiarizedSegment(
                    span=TimeSpan(timedelta(seconds=1), timedelta(seconds=2)),
                    role=SpeakerRole.UNKNOWN,
                    text="",
                    speaker="SPEAKER_01",
                ),
            ),
        ),
    )

    assert rows == [
        ("SPEAKER_01", "клиент"),
        ("SPEAKER_00", "оператор"),
    ]


def test_transcript_rows_mark_client_and_operator_inline() -> None:
    rows = transcript_rows(
        _report(),
        Transcript(
            recording_id=RecordingId("call-ru"),
            language="ru",
            segments=(
                TranscriptSegment(
                    span=TimeSpan(timedelta(seconds=0), timedelta(seconds=1)),
                    text="Здравствуйте",
                ),
                TranscriptSegment(
                    span=TimeSpan(timedelta(seconds=1), timedelta(seconds=2)),
                    text="Хочу записаться",
                ),
            ),
            full_text="Здравствуйте Хочу записаться",
        ),
        DiarizedTranscript(
            recording_id=RecordingId("call-ru"),
            segments=(
                DiarizedSegment(
                    span=TimeSpan(timedelta(seconds=0), timedelta(seconds=1)),
                    role=SpeakerRole.UNKNOWN,
                    text="",
                    speaker="SPEAKER_00",
                ),
                DiarizedSegment(
                    span=TimeSpan(timedelta(seconds=1), timedelta(seconds=2)),
                    role=SpeakerRole.UNKNOWN,
                    text="",
                    speaker="SPEAKER_01",
                ),
            ),
        ),
    )

    assert rows == [
        "[0.0-1.0] оператор / SPEAKER_00: Здравствуйте",
        "[1.0-2.0] клиент / SPEAKER_01: Хочу записаться",
    ]


def _report() -> CallReport:
    return CallReport(
        recording_id=RecordingId("call-ru"),
        satisfaction=Satisfaction.NEUTRAL,
        summary="Клиент получил ответ.",
        key_points=("оператор объяснил статус",),
        generated_at=datetime(2026, 6, 25, 7, 5, tzinfo=MSK),
        question_resolved=QuestionResolution(
            value="partial",
            confidence=0.8,
            evidence=("часть вопроса осталась открытой",),
        ),
        client_satisfaction=ClientSatisfaction(
            value="neutral",
            score_1_5=3,
            confidence=0.625,
            evidence=("тон клиента ровный",),
        ),
        emotional_assessment=EmotionalAssessment(overall="Спокойно."),
        client_speaker="SPEAKER_01",
        operator_speaker="SPEAKER_00",
    )
