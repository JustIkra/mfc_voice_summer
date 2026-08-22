from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from call_analytics.report_view import report_summary_rows, transcript_rows
from call_analytics.service.ports import ReportRenderer, ReportRendererError
from domain import CallReport, DiarizedTranscript, EmotionAnalysis, Transcript


class ReportLabReportRenderer(ReportRenderer):
    async def render(
        self,
        report: CallReport,
        transcript: Transcript,
        diarized: DiarizedTranscript,
        emotions: EmotionAnalysis,
    ) -> bytes:
        try:
            from reportlab.lib import colors  # type: ignore[import-untyped]
            from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
            from reportlab.lib.styles import (  # type: ignore[import-untyped]
                ParagraphStyle,
                getSampleStyleSheet,
            )
            from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
            from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
            from reportlab.platypus import (  # type: ignore[import-untyped]
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ModuleNotFoundError as error:
            raise ReportRendererError.unexpected(
                "reportlab is required for PDF report rendering"
            ) from error

        buffer = BytesIO()
        font = self._register_font(pdfmetrics, TTFont)
        styles = getSampleStyleSheet()
        body = ParagraphStyle(
            "BodyRu",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9,
            leading=12,
        )
        title = ParagraphStyle(
            "TitleRu",
            parent=styles["Title"],
            fontName=font,
            fontSize=15,
            leading=18,
        )
        heading = ParagraphStyle(
            "HeadingRu",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=12,
            leading=15,
        )
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        story: list[Any] = [
            self._paragraph(Paragraph, f"Отчёт по звонку: {report.recording_id.value}.wav", title),
            Spacer(1, 10),
        ]
        rows = report_summary_rows(report)
        table = Table(
            [
                [
                    self._paragraph(Paragraph, key, body),
                    self._paragraph(Paragraph, value, body),
                ]
                for key, value in rows
            ],
            colWidths=[160, 330],
        )
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.extend([table, Spacer(1, 12)])
        sections = [
            ("Краткое содержание", report.summary),
            (
                "Эмоциональный окрас",
                _emotional_text(
                    report.emotional_assessment.overall,
                    report.emotional_assessment.client_emotions,
                    report.emotional_assessment.operator_emotions,
                ),
            ),
            ("Доказательства решения вопроса", "\n".join(report.question_resolved.evidence)),
            ("Доказательства удовлетворённости", "\n".join(report.client_satisfaction.evidence)),
        ]
        for name, value in sections:
            story.extend(
                [
                    self._paragraph(Paragraph, name, heading),
                    self._paragraph(Paragraph, value or "Нет данных", body),
                    Spacer(1, 8),
                ]
            )
        story.append(self._paragraph(Paragraph, "Транскрипт", heading))
        for row in transcript_rows(report, transcript, diarized):
            story.append(self._paragraph(Paragraph, row, body))
        document.build(story)
        return buffer.getvalue()

    async def render_payload(self, payload: Mapping[str, object]) -> bytes:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import (
                ParagraphStyle,
                getSampleStyleSheet,
            )
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ModuleNotFoundError as error:
            raise ReportRendererError.unexpected(
                "reportlab is required for PDF report rendering"
            ) from error

        call = _mapping(payload.get("call"))
        caller = _mapping(payload.get("caller"))
        operator = _mapping(payload.get("operator"))
        analysis = _mapping(payload.get("analysis"))
        transcript = _mapping(payload.get("transcript"))
        buffer = BytesIO()
        font = self._register_font(pdfmetrics, TTFont)
        styles = getSampleStyleSheet()
        body = ParagraphStyle(
            "BodyPayloadRu",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=9,
            leading=12,
        )
        title = ParagraphStyle(
            "TitlePayloadRu",
            parent=styles["Title"],
            fontName=font,
            fontSize=15,
            leading=18,
        )
        heading = ParagraphStyle(
            "HeadingPayloadRu",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=12,
            leading=15,
        )
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        story: list[Any] = [
            self._paragraph(Paragraph, f"Отчёт по звонку: {call.get('id', '')}", title),
            Spacer(1, 10),
        ]
        metadata = [
            ("Файл", ", ".join(_strings(call.get("recording_filenames")))),
            ("Дата", call.get("started_at", "")),
            ("Длительность, сек.", call.get("duration_seconds", "")),
            (
                "Оператор",
                f"{operator.get('name', '')} / ID {operator.get('id', '')} / "
                f"{operator.get('extension', '')}",
            ),
            ("Звонящий", f"{caller.get('name') or 'Имя не определено'} / {caller.get('id', '')}"),
        ]
        table = Table(
            [
                [
                    self._paragraph(Paragraph, key, body),
                    self._paragraph(Paragraph, value, body),
                ]
                for key, value in metadata
            ],
            colWidths=[160, 330],
        )
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.extend([table, Spacer(1, 12)])
        sections = _payload_sections(analysis)
        for name, value in sections:
            story.extend(
                [
                    self._paragraph(Paragraph, name, heading),
                    self._paragraph(Paragraph, value or "Нет данных", body),
                    Spacer(1, 8),
                ]
            )
        story.append(self._paragraph(Paragraph, "Расшифровка", heading))
        segments = transcript.get("segments", ())
        if isinstance(segments, Sequence) and not isinstance(segments, str | bytes):
            for value in segments:
                segment = _mapping(value)
                row = (
                    f"[{segment.get('start_seconds', 0)}-"
                    f"{segment.get('end_seconds', 0)}] "
                    f"{segment.get('speaker', 'unknown')}: {segment.get('text', '')}"
                )
                story.append(self._paragraph(Paragraph, row, body))
        document.build(story)
        return buffer.getvalue()

    def _register_font(self, pdfmetrics: Any, ttfont: Any) -> str:
        for candidate in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]:
            if Path(candidate).exists():
                pdfmetrics.registerFont(ttfont("ReportFont", candidate))
                return "ReportFont"
        return "Helvetica"

    def _paragraph(self, paragraph_cls: Any, value: Any, style: Any) -> Any:
        escaped = html.escape(str(value)).replace("\n", "<br/>")
        return paragraph_cls(escaped, style)


__all__ = ["ReportLabReportRenderer"]


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [str(item) for item in value]


def _payload_sections(analysis: Mapping[str, object]) -> list[tuple[str, object]]:
    emotional = _mapping(analysis.get("emotional_assessment"))
    return [
        ("Краткое содержание", analysis.get("summary", "")),
        (
            "Эмоциональный окрас",
            _emotional_text(
                emotional.get("overall", ""),
                emotional.get("client_emotions", ()),
                emotional.get("operator_emotions", ()),
            ),
        ),
    ]


def _emotional_text(overall: object, client: object, operator: object) -> str:
    return "\n".join(
        [
            str(overall).strip() or "Не определён",
            f"Клиент: {_emotion_values(client)}",
            f"Оператор: {_emotion_values(operator)}",
        ]
    )


def _emotion_values(value: object) -> str:
    labels = {
        "neutral": "спокойствие",
        "happy": "позитив",
        "angry": "раздражение",
        "sad": "грусть",
        "fearful": "тревога",
        "disgusted": "недовольство",
        "surprised": "удивление",
    }
    values = [labels.get(item.strip().lower(), item) for item in _strings(value)]
    return ", ".join(dict.fromkeys(values)) or "не определён"
