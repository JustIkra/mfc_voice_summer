from __future__ import annotations

from datetime import datetime, timedelta, timezone

from call_analytics.service.report_document import build_report_payload
from domain import (
    CallerIdentity,
    CallerNameSource,
    CallRecording,
    CallReport,
    ChannelLayout,
    DiarizedSegment,
    DiarizedTranscript,
    EmotionalAssessment,
    EmotionAnalysis,
    FinalReportDocument,
    OperatorIdentity,
    QuestionResolution,
    QueueIdentity,
    RecordingId,
    Satisfaction,
    SourceRecordingIdentity,
    SpeakerRole,
    TimeSpan,
    Transcript,
    TranscriptSegment,
)

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=MSK)
RID = RecordingId("cdr:group-001")


def _document(caller_name: str | None = "Анна") -> FinalReportDocument:
    span = TimeSpan.from_seconds(0.0, 4.8)
    recording = CallRecording(
        id=RID,
        started_at=NOW,
        duration=timedelta(seconds=91),
        channel_layout=ChannelLayout.MONO,
        queue=QueueIdentity(extension="6500", name="Call_center"),
        caller=CallerIdentity(
            id="79001234567",
            name=None,
            name_source=CallerNameSource.UNKNOWN,
        ),
        operator=OperatorIdentity(id=14, extension="11198", name="Оператор"),
        source_recording=SourceRecordingIdentity(
            acct_id="901",
            filenames=("2026-08/call.wav",),
        ),
    )
    report = CallReport(
        recording_id=RID,
        satisfaction=Satisfaction.SATISFIED,
        summary="Вопрос решён.",
        key_points=("Назван срок",),
        generated_at=NOW,
        caller_name=caller_name,
        caller_name_confidence=0.92 if caller_name else 0.0,
        client_speaker="SPEAKER_01",
        operator_speaker="SPEAKER_00",
        question_resolved=QuestionResolution(value="yes", confidence=0.9),
        emotional_assessment=EmotionalAssessment(overall="Спокойный разговор"),
        risks=(),
        recommendations=("Сохранить стиль ответа",),
    )
    transcript = Transcript(
        recording_id=RID,
        language="ru",
        segments=(TranscriptSegment(span=span, text="Добрый день", confidence=0.96),),
        full_text="Добрый день",
    )
    diarized = DiarizedTranscript(
        recording_id=RID,
        segments=(
            DiarizedSegment(
                span=span,
                role=SpeakerRole.OPERATOR,
                text="Добрый день",
                speaker="SPEAKER_00",
            ),
        ),
    )
    return FinalReportDocument(
        recording=recording,
        report=report,
        transcript=transcript,
        diarized=diarized,
        emotions=EmotionAnalysis(recording_id=RID, segments=()),
    )


def test_report_payload_contains_operator_caller_and_transcript() -> None:
    payload = build_report_payload(_document())

    assert payload["schema_version"] == 1
    assert payload["call"]["id"] == "cdr:group-001"
    assert payload["operator"] == {
        "id": 14,
        "extension": "11198",
        "name": "Оператор",
    }
    assert payload["caller"] == {
        "id": "79001234567",
        "name": "Анна",
        "name_source": "transcript",
        "name_confidence": 0.92,
    }
    assert payload["transcript"]["segments"][0]["speaker"] == "operator"
    assert "audio" not in payload


def test_existing_cdr_caller_name_wins_over_transcript_name() -> None:
    document = _document(caller_name="Другое имя")
    document = FinalReportDocument(
        recording=CallRecording(
            id=document.recording.id,
            started_at=document.recording.started_at,
            duration=document.recording.duration,
            channel_layout=document.recording.channel_layout,
            queue=document.recording.queue,
            caller=CallerIdentity(
                id="79001234567",
                name="Анна из CDR",
                name_source=CallerNameSource.CDR,
                name_confidence=1.0,
            ),
            operator=document.recording.operator,
            source_recording=document.recording.source_recording,
        ),
        report=document.report,
        transcript=document.transcript,
        diarized=document.diarized,
        emotions=document.emotions,
    )

    payload = build_report_payload(document)

    assert payload["caller"]["name"] == "Анна из CDR"
    assert payload["caller"]["name_source"] == "cdr"
