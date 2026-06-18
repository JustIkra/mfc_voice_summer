from datetime import datetime, timedelta, timezone

from domain.recording import RecordingId
from domain.report import CallReport, Satisfaction

MSK = timezone(timedelta(hours=3))


def test_call_report_summarizes_call() -> None:
    report = CallReport(
        recording_id=RecordingId("rec-1"),
        satisfaction=Satisfaction.DISSATISFIED,
        summary="клиент жаловался на сроки",
        key_points=("жалоба", "сроки"),
        generated_at=datetime(2026, 1, 10, 12, 30, tzinfo=MSK),
    )
    assert report.satisfaction is Satisfaction.DISSATISFIED
    assert "сроки" in report.key_points
