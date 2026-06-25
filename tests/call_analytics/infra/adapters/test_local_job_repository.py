from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from call_analytics.infra.adapters.local_dir import LocalJobRepository
from domain import CallProcessingJob, JobStage, JobStatus, RecordingId

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone(timedelta(hours=3)))


async def test_local_job_repository_persists_job_state(tmp_path) -> None:
    repo = LocalJobRepository(tmp_path)
    job = CallProcessingJob.create("job-1", RecordingId("rec-1"), NOW)
    job = job.start_stage(JobStage.TRANSCRIBE).fail_stage(
        JobStage.TRANSCRIBE,
        "TIMEOUT",
        "model timeout",
    )

    await repo.save(job)
    loaded = await repo.get("job-1")

    assert loaded == job
    assert await repo.list_by_status(JobStatus.FAILED) == [job]


async def test_local_job_repository_preserves_existing_job_when_save_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = LocalJobRepository(tmp_path)
    pending = CallProcessingJob.create("job-1", RecordingId("rec-1"), NOW)
    await repo.save(pending)
    original_write_text = Path.write_text

    def failing_write_text(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if '"status": "done"' in data:
            original_write_text(path, "{", encoding=encoding, errors=errors, newline=newline)
            raise OSError("disk write interrupted")
        return original_write_text(
            path,
            data,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "write_text", failing_write_text)
    done = pending.start_stage(JobStage.TRANSCRIBE)
    done = done.complete_stage(JobStage.TRANSCRIBE)
    done = done.start_stage(JobStage.DIARIZE)
    done = done.complete_stage(JobStage.DIARIZE)
    done = done.start_stage(JobStage.EMOTION)
    done = done.complete_stage(JobStage.EMOTION)
    done = done.start_stage(JobStage.REPORT)
    done = done.complete_stage(JobStage.REPORT)

    with pytest.raises(OSError, match="disk write interrupted"):
        await repo.save(done)

    assert await repo.get("job-1") == pending
