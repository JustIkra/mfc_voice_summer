from datetime import datetime, timedelta, timezone

import pytest

from domain.errors import InvalidJobTransition
from domain.job import STAGE_ORDER, CallProcessingJob, JobStage, JobStatus
from domain.recording import RecordingId

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 1, 10, 12, 0, tzinfo=MSK)


def _job() -> CallProcessingJob:
    return CallProcessingJob.create("job-1", RecordingId("rec-1"), NOW)


def test_fresh_job_is_pending_at_first_stage() -> None:
    job = _job()
    assert job.status is JobStatus.PENDING
    assert job.next_stage() is JobStage.TRANSCRIBE
    assert job.completed_stages == frozenset()


def test_happy_path_runs_all_stages_to_done() -> None:
    job = _job()
    for stage in STAGE_ORDER:
        job = job.start_stage(stage)
        assert job.status is JobStatus.RUNNING
        job = job.complete_stage(stage)
    assert job.status is JobStatus.DONE
    assert job.next_stage() is None


def test_start_counts_attempts() -> None:
    job = _job().start_stage(JobStage.TRANSCRIBE)
    assert job.attempts[JobStage.TRANSCRIBE] == 1


def test_cannot_start_out_of_order_stage() -> None:
    job = _job()
    with pytest.raises(InvalidJobTransition):
        job.start_stage(JobStage.REPORT)


def test_cannot_complete_when_not_running() -> None:
    job = _job()
    with pytest.raises(InvalidJobTransition):
        job.complete_stage(JobStage.TRANSCRIBE)


def test_recover_interrupted_running_job_returns_to_pending_stage() -> None:
    job = _job().start_stage(JobStage.TRANSCRIBE)

    recovered = job.recover_interrupted()

    assert recovered.status is JobStatus.PENDING
    assert recovered.next_stage() is JobStage.TRANSCRIBE
    assert recovered.attempts[JobStage.TRANSCRIBE] == 1


def test_fail_then_retry_keeps_completed_and_reruns_failed_stage() -> None:
    job = _job()
    job = job.start_stage(JobStage.TRANSCRIBE).complete_stage(JobStage.TRANSCRIBE)
    job = job.start_stage(JobStage.DIARIZE).fail_stage(JobStage.DIARIZE, "TIMEOUT", "slow")
    assert job.status is JobStatus.FAILED
    assert job.last_error == ("TIMEOUT", "slow")

    job = job.retry()
    assert job.status is JobStatus.PENDING
    assert job.last_error is None
    assert JobStage.TRANSCRIBE in job.completed_stages
    assert job.next_stage() is JobStage.DIARIZE
    assert job.attempts[JobStage.TRANSCRIBE] == 1

    job = job.start_stage(JobStage.DIARIZE)
    assert job.attempts[JobStage.DIARIZE] == 2


def test_retry_only_from_failed() -> None:
    with pytest.raises(InvalidJobTransition):
        _job().retry()
