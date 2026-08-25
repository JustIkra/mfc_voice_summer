from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from domain.errors import InvalidJobTransition
from domain.recording import RecordingId


class JobStage(Enum):
    TRANSCRIBE = "transcribe"
    DIARIZE = "diarize"
    EMOTION = "emotion"
    REPORT = "report"


STAGE_ORDER: tuple[JobStage, ...] = (
    JobStage.TRANSCRIBE,
    JobStage.DIARIZE,
    JobStage.EMOTION,
    JobStage.REPORT,
)


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"
    SKIPPED_EMPTY = "skipped_empty"


@dataclass(frozen=True, slots=True)
class CallProcessingJob:
    """Агрегат-машина состояний обработки одного звонка.

    Переходы возвращают новый экземпляр (иммутабельность). Стадии идут
    строго по `STAGE_ORDER`; нарушение порядка или статуса — это
    `InvalidJobTransition`. `next_stage()` всегда указывает на первую
    незавершённую стадию, поэтому повтор (`retry`) переигрывает именно
    упавшую стадию, не теряя уже посчитанные.
    """

    id: str
    recording_id: RecordingId
    status: JobStatus
    completed_stages: frozenset[JobStage]
    attempts: Mapping[JobStage, int]
    last_error: tuple[str, str] | None
    created_at: datetime

    @classmethod
    def create(cls, job_id: str, recording_id: RecordingId, now: datetime) -> CallProcessingJob:
        return cls(
            id=job_id,
            recording_id=recording_id,
            status=JobStatus.PENDING,
            completed_stages=frozenset(),
            attempts={},
            last_error=None,
            created_at=now,
        )

    def next_stage(self) -> JobStage | None:
        for stage in STAGE_ORDER:
            if stage not in self.completed_stages:
                return stage
        return None

    def start_stage(self, stage: JobStage) -> CallProcessingJob:
        if self.status is not JobStatus.PENDING:
            raise InvalidJobTransition(f"нельзя начать стадию из статуса {self.status.name}")
        if stage is not self.next_stage():
            raise InvalidJobTransition(f"стадия {stage.name} не является следующей")
        attempts = dict(self.attempts)
        attempts[stage] = attempts.get(stage, 0) + 1
        return replace(self, status=JobStatus.RUNNING, attempts=attempts)

    def complete_stage(self, stage: JobStage) -> CallProcessingJob:
        if self.status is not JobStatus.RUNNING:
            raise InvalidJobTransition(f"нельзя завершить стадию из статуса {self.status.name}")
        if stage is not self.next_stage():
            raise InvalidJobTransition(f"завершается не текущая стадия {stage.name}")
        completed = self.completed_stages | {stage}
        done = all(s in completed for s in STAGE_ORDER)
        return replace(
            self,
            completed_stages=completed,
            status=JobStatus.DONE if done else JobStatus.PENDING,
            last_error=None,
        )

    def fail_stage(self, stage: JobStage, kind: str, message: str) -> CallProcessingJob:
        if self.status is not JobStatus.RUNNING:
            raise InvalidJobTransition(f"нельзя пометить ошибку из статуса {self.status.name}")
        return replace(self, status=JobStatus.FAILED, last_error=(kind, message))

    def fail_before_processing(self, kind: str, message: str) -> CallProcessingJob:
        if self.status is not JobStatus.PENDING:
            raise InvalidJobTransition(
                f"предварительная ошибка возможна только из PENDING, текущий {self.status.name}"
            )
        return replace(self, status=JobStatus.FAILED, last_error=(kind, message))

    def skip_empty(self) -> CallProcessingJob:
        if self.status is not JobStatus.RUNNING:
            raise InvalidJobTransition(
                f"пропуск пустой записи возможен только из RUNNING, текущий {self.status.name}"
            )
        return replace(self, status=JobStatus.SKIPPED_EMPTY, last_error=None)

    def retry(self) -> CallProcessingJob:
        if self.status is not JobStatus.FAILED:
            raise InvalidJobTransition(
                f"повтор возможен только из FAILED, текущий {self.status.name}"
            )
        return replace(self, status=JobStatus.PENDING, last_error=None)

    def restart(self) -> CallProcessingJob:
        if self.status is not JobStatus.FAILED:
            raise InvalidJobTransition(
                f"перезапуск возможен только из FAILED, текущий {self.status.name}"
            )
        return replace(
            self,
            status=JobStatus.PENDING,
            completed_stages=frozenset(),
            last_error=None,
        )

    def cancel(self) -> CallProcessingJob:
        if self.status is not JobStatus.PENDING:
            raise InvalidJobTransition(
                f"отмена возможна только из PENDING, текущий {self.status.name}"
            )
        return replace(self, status=JobStatus.CANCELED)

    def resume(self) -> CallProcessingJob:
        if self.status is not JobStatus.CANCELED:
            raise InvalidJobTransition(
                f"возврат в очередь возможен только из CANCELED, текущий {self.status.name}"
            )
        return replace(self, status=JobStatus.PENDING, last_error=None)

    def recover_interrupted(self) -> CallProcessingJob:
        if self.status is not JobStatus.RUNNING:
            raise InvalidJobTransition(
                f"recovery возможен только из RUNNING, текущий {self.status.name}"
            )
        return replace(
            self,
            status=JobStatus.PENDING,
            completed_stages=frozenset(),
            last_error=None,
        )


__all__ = ["STAGE_ORDER", "CallProcessingJob", "JobStage", "JobStatus"]
