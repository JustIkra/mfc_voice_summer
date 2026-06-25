from __future__ import annotations

import html
from io import BytesIO
from pathlib import Path
from typing import Any

from call_analytics.infra.ports import ReportRenderer
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
            raise RuntimeError("reportlab is required for PDF report rendering") from error

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
        rows = [
            ("Решён ли вопрос", report.question_resolved.value),
            ("Уверенность", report.question_resolved.confidence),
            ("Удовлетворённость клиента", report.client_satisfaction.value),
            ("Оценка 1-5", report.client_satisfaction.score_1_5),
        ]
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
            ("Эмоциональная оценка", report.emotional_assessment.overall),
            ("Доказательства решения вопроса", "\n".join(report.question_resolved.evidence)),
            ("Доказательства удовлетворённости", "\n".join(report.client_satisfaction.evidence)),
            ("Риски", "\n".join(report.risks)),
            ("Рекомендации", "\n".join(report.recommendations)),
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
        for segment in transcript.segments:
            story.append(
                self._paragraph(
                    Paragraph,
                    (
                        f"[{segment.span.start.total_seconds():.1f}-"
                        f"{segment.span.end.total_seconds():.1f}] {segment.text}"
                    ),
                    body,
                )
            )
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
