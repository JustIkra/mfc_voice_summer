from __future__ import annotations

from call_analytics.web import create_app


def test_public_openapi_has_no_recording_or_job_mutations() -> None:
    paths = create_app().openapi()["paths"]

    assert "/api/recordings" not in paths
    assert "/api/recordings/{recording_id}/jobs" not in paths
    assert "/api/jobs/{job_id}/retry" not in paths
    assert "/api/jobs/{job_id}/cancel" not in paths
    assert set(paths) == {
        "/",
        "/api/calls",
        "/api/calls/{call_id}/audio",
        "/api/calls/{call_id}/report",
        "/api/calls/{call_id}/report.pdf",
        "/api/dashboard/summary",
        "/api/operators",
        "/api/sync/status",
        "/favicon.ico",
        "/health",
    }
