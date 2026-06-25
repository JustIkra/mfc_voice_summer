from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
