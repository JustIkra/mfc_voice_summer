from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from call_analytics.infra.adapters.in_memory import (
    InMemoryDashboardRepository,
    InMemorySyncRunRepository,
)
from call_analytics.service import DashboardService
from call_analytics.service.dashboard import (
    CallListItem,
    DashboardSummary,
    OperatorSummary,
)
from call_analytics.service.ports import (
    ArchivedRecording,
    ArchivedRecordingFile,
    FinalReportRepository,
    RecordingArchive,
    RecordingStorageStatus,
)
from call_analytics.web import create_app
from domain import CallProcessingJob, FinalReportDocument, RecordingId

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=MSK)
CALL_ID = "cdr:group-001"
OGG_BYTES = b"OggS0123456789"
REPORT_PAYLOAD: dict[str, object] = {
    "schema_version": 1,
    "call": {
        "id": CALL_ID,
        "acct_id": "901",
        "recording_filenames": ["2026-08/call.wav"],
        "started_at": NOW.isoformat(),
        "duration_seconds": 180.0,
        "queue": {"extension": "6500", "name": "Call_center"},
    },
    "caller": {
        "id": "79000000001",
        "name": "Анна",
        "name_source": "transcript",
        "name_confidence": 0.92,
    },
    "operator": {"id": 14, "extension": "11198", "name": "Оператор"},
    "analysis": {
        "satisfaction": "satisfied",
        "question_resolved": {"value": "yes", "confidence": 0.9, "evidence": []},
        "client_satisfaction": {
            "value": "satisfied",
            "score_1_5": 5,
            "confidence": 0.9,
            "evidence": [],
        },
        "summary": "Вопрос решён.",
        "key_points": ["Назван срок"],
        "emotional_assessment": {
            "overall": "Спокойный разговор",
            "client_emotions": [],
            "operator_emotions": [],
            "evidence": [],
        },
        "risks": [],
        "recommendations": [],
    },
    "transcript": {
        "language": "ru",
        "segments": [
            {
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "speaker": "operator",
                "text": "Добрый день",
                "confidence": 0.96,
            }
        ],
    },
    "generated_at": NOW.isoformat(),
}


class FakeFinalReportRepository(FinalReportRepository):
    async def finalize(self, job: CallProcessingJob, document: FinalReportDocument) -> None:
        raise AssertionError("finalize is not used by web tests")

    async def load_payload(self, recording_id: RecordingId) -> dict[str, object] | None:
        return REPORT_PAYLOAD if recording_id.value == CALL_ID else None


class FakeRecordingArchive(RecordingArchive):
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    async def store(self, recording_id, audio) -> ArchivedRecording:
        raise AssertionError("store is not used by web tests")

    async def locate(self, recording_id: RecordingId) -> ArchivedRecordingFile | None:
        if recording_id.value != CALL_ID or self.path is None:
            return None
        return ArchivedRecordingFile(self.path, "audio/ogg", self.path.stat().st_size)

    async def storage_status(self) -> RecordingStorageStatus:
        return RecordingStorageStatus.from_usage(100, 10, 90, reserve_bytes=2)


def build_client(archive: RecordingArchive | None = None) -> TestClient:
    summary = DashboardSummary(
        total_calls=2,
        resolved_calls=1,
        average_duration_seconds=180.0,
        attention_calls=1,
        satisfaction={"satisfied": 1, "neutral": 0, "dissatisfied": 1},
        resolution={"yes": 1, "partial": 0, "no": 1, "unknown": 0},
    )
    operators = [
        OperatorSummary(
            id=14,
            extension="11198",
            name="Оператор",
            total_calls=2,
            satisfied_percent=50,
            resolved_percent=50,
            attention_calls=1,
        )
    ]
    calls = [
        CallListItem(
            call_id=CALL_ID,
            recording_filenames=("2026-08/call.wav",),
            started_at=NOW,
            duration_seconds=180.0,
            caller_id="79000000001",
            caller_name="Анна",
            operator_id=14,
            operator_extension="11198",
            operator_name="Оператор",
            summary="Вопрос решён.",
            satisfaction="satisfied",
            question_resolved="yes",
        )
    ]
    service = DashboardService(
        dashboard=InMemoryDashboardRepository(
            summary,
            operators,
            calls,
            processing={"pending": 3, "running": 1, "done": 2, "failed": 1},
        ),
        reports=FakeFinalReportRepository(),
        sync_runs=InMemorySyncRunRepository(),
        archive=archive or FakeRecordingArchive(),
    )
    return TestClient(create_app(lambda: service, clock=lambda: NOW))


def test_dashboard_summary_and_operator_endpoints() -> None:
    client = build_client()

    summary = client.get("/api/dashboard/summary")
    operators = client.get("/api/operators")

    assert summary.status_code == 200
    assert summary.json() == {
        "total_calls": 2,
        "resolved_calls": 1,
        "average_duration_seconds": 180.0,
        "attention_calls": 1,
        "satisfaction": {"satisfied": 1, "neutral": 0, "dissatisfied": 1},
        "resolution": {"yes": 1, "partial": 0, "no": 1, "unknown": 0},
    }
    assert operators.json()[0]["operator_id"] == 14
    assert operators.json()[0]["operator_name"] == "Оператор"
    assert operators.json()[0]["resolved_percent"] == 50


def test_call_list_is_server_paginated_and_has_no_audio_fields() -> None:
    response = build_client().get(
        "/api/calls",
        params={
            "page": 1,
            "page_size": 50,
            "operator_extension": "11198",
            "sort": "asc",
        },
    )

    assert response.status_code == 200
    assert response.json()["page_size"] == 50
    assert response.json()["total_items"] == 1
    assert response.json()["items"][0]["call_id"] == CALL_ID
    assert "audio" not in response.text.lower()


def test_report_and_pdf_are_loaded_from_canonical_payload() -> None:
    client = build_client()

    report = client.get(f"/api/calls/{CALL_ID}/report")
    pdf = client.get(f"/api/calls/{CALL_ID}/report.pdf")

    assert report.status_code == 200
    assert report.json()["transcript"]["segments"][0]["text"] == "Добрый день"
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_report_exposes_audio_and_range_endpoint(tmp_path: Path) -> None:
    audio_path = tmp_path / "call.ogg"
    audio_path.write_bytes(OGG_BYTES)
    client = build_client(FakeRecordingArchive(audio_path))

    report = client.get(f"/api/calls/{CALL_ID}/report")
    audio = client.get(
        f"/api/calls/{CALL_ID}/audio",
        headers={"Range": "bytes=0-3"},
    )

    assert report.json()["audio"] == {
        "available": True,
        "url": f"/api/calls/{quote(CALL_ID, safe='')}/audio",
        "mime_type": "audio/ogg",
    }
    assert audio.status_code == 206
    assert audio.headers["content-type"].startswith("audio/ogg")
    assert audio.headers["accept-ranges"] == "bytes"
    assert audio.content == OGG_BYTES[:4]


def test_missing_report_and_invalid_filters_are_explicit() -> None:
    client = build_client()

    assert client.get("/api/calls/missing/report").status_code == 404
    assert client.get("/api/calls/missing/audio").status_code == 404
    assert (
        client.get(
            "/api/calls",
            params={"date_from": "2026-08-22", "date_to": "2026-08-01"},
        ).status_code
        == 422
    )
    assert client.get("/api/calls", params={"satisfaction": "excellent"}).status_code == 422
    assert client.get("/api/calls", params={"question_resolved": "maybe"}).status_code == 422
    assert client.get("/api/calls", params={"sort": "sideways"}).status_code == 422
    assert client.get("/api/calls", params={"page_size": 101}).status_code == 422


def test_mutating_recording_and_job_routes_are_removed() -> None:
    client = build_client()

    assert client.post("/api/recordings", files={"file": ("x.wav", b"x")}).status_code == 404
    assert client.post("/api/recordings/call/jobs").status_code == 404
    assert client.post("/api/jobs/call/retry").status_code == 404
    assert client.delete("/api/recordings/call/report").status_code == 404


def test_sync_status_reports_never_before_first_run() -> None:
    response = build_client().get("/api/sync/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "never",
        "processing": {"pending": 3, "running": 1, "done": 2, "failed": 1},
        "storage": {
            "total_bytes": 100,
            "used_bytes": 10,
            "free_bytes": 90,
            "used_percent": 10,
            "state": "ok",
        },
    }
