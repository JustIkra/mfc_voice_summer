from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime

from call_analytics.service.dashboard import (
    CallPage,
    CallPageRequest,
    DashboardFilter,
    DashboardSummary,
    OperatorSummary,
    SyncStatus,
)
from domain import (
    CallProcessingJob,
    CallRecording,
    DiscoveredCall,
    FinalReportDocument,
    JobStatus,
    Period,
    RecordingId,
)


class CallRepository(ABC):
    @abstractmethod
    async def contains(self, recording_id: RecordingId) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def register(self, recording: CallRecording, job: CallProcessingJob) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def register_skipped(
        self,
        call: DiscoveredCall,
        reason: str,
        now: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def register_failed(
        self,
        call: DiscoveredCall,
        kind: str,
        reason: str,
        now: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load_recording(self, recording_id: RecordingId) -> CallRecording | None:
        raise NotImplementedError

    @abstractmethod
    async def status(self, recording_id: RecordingId) -> JobStatus | None:
        raise NotImplementedError

    @abstractmethod
    async def mark_skipped_empty(self, recording_id: RecordingId, reason: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_retryable(self, max_attempts: int) -> Sequence[CallRecording]:
        raise NotImplementedError

    @abstractmethod
    async def list_done_recordings(self) -> Sequence[CallRecording]:
        raise NotImplementedError


class FinalReportRepository(ABC):
    @abstractmethod
    async def finalize(self, job: CallProcessingJob, document: FinalReportDocument) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load_payload(self, recording_id: RecordingId) -> dict[str, object] | None:
        raise NotImplementedError


class SyncRunRepository(ABC):
    @abstractmethod
    async def start(self, period: Period, started_at: datetime) -> int | None:
        raise NotImplementedError

    @abstractmethod
    async def finish(
        self,
        run_id: int,
        finished_at: datetime,
        status: str,
        discovered: int,
        queued: int,
        skipped: int,
        failed: int,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def last(self) -> SyncStatus | None:
        raise NotImplementedError


class DashboardRepository(ABC):
    @abstractmethod
    async def summary(self, filters: DashboardFilter) -> DashboardSummary:
        raise NotImplementedError

    @abstractmethod
    async def operators(self, filters: DashboardFilter) -> Sequence[OperatorSummary]:
        raise NotImplementedError

    @abstractmethod
    async def list_calls(self, request: CallPageRequest) -> CallPage:
        raise NotImplementedError

    @abstractmethod
    async def processing_counts(self) -> Mapping[str, int]:
        raise NotImplementedError


__all__ = [
    "CallRepository",
    "DashboardRepository",
    "FinalReportRepository",
    "SyncRunRepository",
]
