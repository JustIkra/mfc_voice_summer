from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from call_analytics.service.ports import JobRepository
from domain import CallProcessingJob, JobStage, JobStatus, RecordingId


class LocalJobRepository(JobRepository):
    def __init__(self, root: Path) -> None:
        self._directory = root / "jobs"

    async def save(self, job: CallProcessingJob) -> None:
        path = self._path(job.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._to_json(job), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def get(self, job_id: str) -> CallProcessingJob | None:
        path = self._path(job_id)
        if not path.is_file():
            return None
        return self._from_json(json.loads(path.read_text(encoding="utf-8")))

    async def list_by_status(self, status: JobStatus) -> Sequence[CallProcessingJob]:
        if not self._directory.is_dir():
            return []
        jobs = [
            self._from_json(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self._directory.glob("*.json"))
        ]
        return [job for job in jobs if job.status is status]

    def _path(self, job_id: str) -> Path:
        return self._directory / f"{job_id}.json"

    def _to_json(self, job: CallProcessingJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "recording_id": job.recording_id.value,
            "status": job.status.value,
            "completed_stages": [
                stage.value
                for stage in sorted(
                    job.completed_stages,
                    key=lambda item: item.value,
                )
            ],
            "attempts": {stage.value: count for stage, count in job.attempts.items()},
            "last_error": list(job.last_error) if job.last_error is not None else None,
            "created_at": job.created_at.isoformat(),
        }

    def _from_json(self, payload: dict[str, Any]) -> CallProcessingJob:
        return CallProcessingJob(
            id=str(payload["id"]),
            recording_id=RecordingId(str(payload["recording_id"])),
            status=JobStatus(str(payload["status"])),
            completed_stages=frozenset(
                JobStage(str(stage)) for stage in payload.get("completed_stages", ())
            ),
            attempts={
                JobStage(str(stage)): int(count)
                for stage, count in dict(payload.get("attempts", {})).items()
            },
            last_error=tuple(payload["last_error"]) if payload.get("last_error") else None,
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


__all__ = ["LocalJobRepository"]
