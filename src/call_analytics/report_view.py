from __future__ import annotations

from math import floor
from typing import Any

from domain import CallReport, Satisfaction

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


__all__ = [
    "format_confidence",
    "localize_client_satisfaction",
    "localize_question_resolution",
    "localize_satisfaction",
    "report_summary_rows",
    "report_to_public_json",
]
