from __future__ import annotations

from datetime import timedelta

from domain import (
    CallerNameSource,
    DiarizedSegment,
    FinalReportDocument,
    TimeSpan,
)


def build_report_payload(document: FinalReportDocument) -> dict[str, object]:
    recording = document.recording
    report = document.report
    caller_name = recording.caller.name
    caller_name_source = recording.caller.name_source
    caller_name_confidence = recording.caller.name_confidence
    if caller_name is None and report.caller_name:
        caller_name = report.caller_name
        caller_name_source = CallerNameSource.TRANSCRIPT
        caller_name_confidence = report.caller_name_confidence

    source = recording.source_recording
    queue = recording.queue
    operator = recording.operator
    transcript_segments = [
        {
            "start_seconds": segment.span.start.total_seconds(),
            "end_seconds": segment.span.end.total_seconds(),
            "speaker": _speaker_role(document, segment.span),
            "text": segment.text,
            "confidence": segment.confidence,
        }
        for segment in document.transcript.segments
    ]
    return {
        "schema_version": 1,
        "call": {
            "id": recording.id.value,
            "acct_id": source.acct_id if source else None,
            "recording_filenames": list(source.filenames) if source else [],
            "started_at": recording.started_at.isoformat(),
            "duration_seconds": recording.duration.total_seconds(),
            "queue": {
                "extension": queue.extension if queue else None,
                "name": queue.name if queue else None,
            },
        },
        "caller": {
            "id": recording.caller.id,
            "name": caller_name,
            "name_source": caller_name_source.value,
            "name_confidence": caller_name_confidence,
        },
        "operator": (
            {
                "id": operator.id,
                "extension": operator.extension,
                "name": operator.name,
            }
            if operator
            else None
        ),
        "analysis": {
            "satisfaction": report.satisfaction.name.lower(),
            "question_resolved": {
                "value": report.question_resolved.value,
                "confidence": report.question_resolved.confidence,
                "evidence": list(report.question_resolved.evidence),
            },
            "client_satisfaction": {
                "value": report.client_satisfaction.value,
                "score_1_5": report.client_satisfaction.score_1_5,
                "confidence": report.client_satisfaction.confidence,
                "evidence": list(report.client_satisfaction.evidence),
            },
            "summary": report.summary,
            "key_points": list(report.key_points),
            "emotional_assessment": {
                "overall": report.emotional_assessment.overall,
                "client_emotions": list(report.emotional_assessment.client_emotions),
                "operator_emotions": list(report.emotional_assessment.operator_emotions),
                "evidence": list(report.emotional_assessment.evidence),
            },
            "risks": list(report.risks),
            "recommendations": list(report.recommendations),
        },
        "transcript": {
            "language": document.transcript.language,
            "segments": transcript_segments,
        },
        "generated_at": report.generated_at.isoformat(),
    }


def _speaker_role(document: FinalReportDocument, span: TimeSpan) -> str:
    speaker = _best_speaker(span, document.diarized.segments)
    if speaker == document.report.operator_speaker:
        return "operator"
    if speaker == document.report.client_speaker:
        return "client"
    return "unknown"


def _best_speaker(span: TimeSpan, segments: tuple[DiarizedSegment, ...]) -> str | None:
    overlap_by_speaker: dict[str, float] = {}
    for segment in segments:
        if segment.speaker is None:
            continue
        overlap = _overlap(span, segment.span).total_seconds()
        if overlap > 0:
            overlap_by_speaker[segment.speaker] = (
                overlap_by_speaker.get(segment.speaker, 0.0) + overlap
            )
    if not overlap_by_speaker:
        return None
    return max(overlap_by_speaker.items(), key=lambda item: item[1])[0]


def _overlap(first: TimeSpan, second: TimeSpan) -> timedelta:
    return max(timedelta(), min(first.end, second.end) - max(first.start, second.start))


__all__ = ["build_report_payload"]
