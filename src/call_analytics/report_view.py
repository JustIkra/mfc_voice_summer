from __future__ import annotations

from math import floor
from typing import Any

from domain import (
    CallReport,
    DiarizedTranscript,
    Satisfaction,
    SpeakerRole,
    TimeSpan,
    Transcript,
)

_SATISFACTION_LABELS = {
    Satisfaction.SATISFIED: "удовлетворён",
    Satisfaction.NEUTRAL: "нейтральная",
    Satisfaction.DISSATISFIED: "не удовлетворён",
}
_QUESTION_RESOLUTION_LABELS = {
    "yes": "да",
    "no": "нет",
    "partial": "частично",
    "unknown": "неизвестно",
}
_CLIENT_SATISFACTION_LABELS = {
    "satisfied": "удовлетворён",
    "neutral": "нейтральная",
    "dissatisfied": "не удовлетворён",
    "unknown": "неизвестно",
}


def report_summary_rows(report: CallReport) -> list[tuple[str, str]]:
    return [
        ("Решён ли вопрос", localize_question_resolution(report.question_resolved.value)),
        ("Уверенность", format_confidence(report.question_resolved.confidence)),
        (
            "Удовлетворённость клиента",
            localize_client_satisfaction(report.client_satisfaction.value),
        ),
    ]


def report_to_public_json(report: CallReport) -> dict[str, Any]:
    return {
        "recording_id": report.recording_id.value,
        "satisfaction": localize_satisfaction(report.satisfaction),
        "voice_sources": {
            "client": report.client_speaker,
            "operator": report.operator_speaker,
        },
        "summary": report.summary,
        "key_points": list(report.key_points),
        "generated_at": report.generated_at.isoformat(),
        "question_resolved": {
            "value": localize_question_resolution(report.question_resolved.value),
            "confidence": format_confidence(report.question_resolved.confidence),
            "evidence": list(report.question_resolved.evidence),
        },
        "client_satisfaction": {
            "value": localize_client_satisfaction(report.client_satisfaction.value),
            "confidence": format_confidence(report.client_satisfaction.confidence),
            "evidence": list(report.client_satisfaction.evidence),
        },
        "emotional_assessment": {
            "overall": report.emotional_assessment.overall,
            "client_emotions": list(report.emotional_assessment.client_emotions),
            "operator_emotions": list(report.emotional_assessment.operator_emotions),
            "evidence": list(report.emotional_assessment.evidence),
        },
        "risks": list(report.risks),
        "recommendations": list(report.recommendations),
    }


def localize_satisfaction(value: Satisfaction) -> str:
    return _SATISFACTION_LABELS.get(value, "неизвестно")


def localize_question_resolution(value: str) -> str:
    return _QUESTION_RESOLUTION_LABELS.get(value.strip().lower(), value)


def localize_client_satisfaction(value: str) -> str:
    return _CLIENT_SATISFACTION_LABELS.get(value.strip().lower(), value)


def format_confidence(value: float) -> str:
    percent = max(0, min(100, floor(value * 100 + 0.5)))
    return f"{percent}%"


def voice_source_rows(report: CallReport, diarized: DiarizedTranscript) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(speaker: str | None, label: str) -> None:
        if not speaker or speaker == "unknown" or speaker in seen:
            return
        seen.add(speaker)
        rows.append((speaker, label))

    add(report.client_speaker, "клиент")
    add(report.operator_speaker, "оператор")
    for segment in diarized.segments:
        if segment.role is SpeakerRole.CLIENT:
            add(segment.speaker, "клиент")
        elif segment.role is SpeakerRole.OPERATOR:
            add(segment.speaker, "оператор")
    for segment in diarized.segments:
        add(segment.speaker, "роль не определена")
    return rows


def transcript_rows(
    report: CallReport,
    transcript: Transcript,
    diarized: DiarizedTranscript,
) -> list[str]:
    return [
        (
            f"[{segment.span.start.total_seconds():.1f}-"
            f"{segment.span.end.total_seconds():.1f}] "
            f"{_speaker_label(_best_speaker(segment.span, diarized), report)}: "
            f"{segment.text}"
        )
        for segment in transcript.segments
    ]


def _best_speaker(span: TimeSpan, diarized: DiarizedTranscript) -> str | None:
    totals: dict[str, float] = {}
    for segment in diarized.segments:
        if segment.speaker is None:
            continue
        start = max(span.start, segment.span.start)
        end = min(span.end, segment.span.end)
        overlap = (end - start).total_seconds()
        if overlap > 0:
            totals[segment.speaker] = totals.get(segment.speaker, 0.0) + overlap
    if not totals:
        return None
    return max(totals.items(), key=lambda item: item[1])[0]


def _speaker_label(speaker: str | None, report: CallReport) -> str:
    if speaker is None:
        return "источник не определён"
    if speaker == report.client_speaker:
        return f"клиент / {speaker}"
    if speaker == report.operator_speaker:
        return f"оператор / {speaker}"
    return f"роль не определена / {speaker}"


__all__ = [
    "format_confidence",
    "localize_client_satisfaction",
    "localize_question_resolution",
    "localize_satisfaction",
    "report_summary_rows",
    "report_to_public_json",
    "transcript_rows",
    "voice_source_rows",
]
