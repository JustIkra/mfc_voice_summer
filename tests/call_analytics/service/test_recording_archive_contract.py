from __future__ import annotations

from call_analytics.service.ports.archive import (
    RecordingArchiveError,
    RecordingStorageStatus,
)


def test_storage_status_thresholds() -> None:
    assert RecordingStorageStatus.from_usage(100, 70, 30, reserve_bytes=2).state == "ok"
    assert RecordingStorageStatus.from_usage(100, 85, 15, reserve_bytes=2).state == "warning"
    assert RecordingStorageStatus.from_usage(100, 95, 5, reserve_bytes=2).state == "critical"
    assert RecordingStorageStatus.from_usage(100, 99, 1, reserve_bytes=2).state == "full"


def test_storage_status_reports_used_percent() -> None:
    status = RecordingStorageStatus.from_usage(200, 50, 150, reserve_bytes=2)

    assert status.total_bytes == 200
    assert status.used_bytes == 50
    assert status.free_bytes == 150
    assert status.used_percent == 25


def test_archive_error_does_not_expose_provider_secrets() -> None:
    error = RecordingArchiveError("ARCHIVE_IO", "archive write failed")

    assert error.kind == "ARCHIVE_IO"
    assert str(error) == "archive write failed"
