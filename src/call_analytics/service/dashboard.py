from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from domain import RecordingId

if TYPE_CHECKING:
    from call_analytics.service.ports.persistence import (
        DashboardRepository,
        FinalReportRepository,
        SyncRunRepository,
    )


@dataclass(frozen=True, slots=True)
class DashboardFilter:
    date_from: datetime
    date_to: datetime
    operator_id: int | None = None
    satisfaction: str | None = None
    query: str = ""


@dataclass(frozen=True, slots=True)
class CallPageRequest:
    filters: DashboardFilter
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    total_calls: int
    resolved_calls: int
    average_duration_seconds: float
    attention_calls: int
    satisfaction: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class OperatorSummary:
    id: int
    extension: str
    name: str
    total_calls: int
    satisfied_percent: int
    attention_calls: int


@dataclass(frozen=True, slots=True)
class CallListItem:
    call_id: str
    recording_filenames: tuple[str, ...]
    started_at: datetime
    duration_seconds: float
    caller_id: str | None
    caller_name: str | None
    operator_id: int
    operator_extension: str
    operator_name: str
    summary: str
    satisfaction: str
    question_resolved: str


@dataclass(frozen=True, slots=True)
class CallPage:
    items: Sequence[CallListItem]
    page: int
    page_size: int
    total_items: int


@dataclass(frozen=True, slots=True)
class SyncStatus:
    status: str
    started_at: datetime
    finished_at: datetime | None
    discovered: int
    queued: int
    skipped: int
    failed: int


class DashboardService:
    def __init__(
        self,
        dashboard: DashboardRepository,
        reports: FinalReportRepository,
        sync_runs: SyncRunRepository,
    ) -> None:
        self._dashboard = dashboard
        self._reports = reports
        self._sync_runs = sync_runs

    async def summary(self, filters: DashboardFilter) -> DashboardSummary:
        return await self._dashboard.summary(filters)

    async def operators(self, filters: DashboardFilter) -> Sequence[OperatorSummary]:
        return await self._dashboard.operators(filters)

    async def calls(self, request: CallPageRequest) -> CallPage:
        return await self._dashboard.list_calls(request)

    async def report(self, recording_id: RecordingId) -> dict[str, object] | None:
        return await self._reports.load_payload(recording_id)

    async def sync_status(self) -> SyncStatus | None:
        return await self._sync_runs.last()


__all__ = [
    "CallListItem",
    "CallPage",
    "CallPageRequest",
    "DashboardFilter",
    "DashboardService",
    "DashboardSummary",
    "OperatorSummary",
    "SyncStatus",
]
