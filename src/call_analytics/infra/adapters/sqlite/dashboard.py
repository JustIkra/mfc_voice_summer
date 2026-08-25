from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime

from call_analytics.infra.adapters.sqlite.database import SqliteDatabase
from call_analytics.service.ports import (
    CallListItem,
    CallPage,
    CallPageRequest,
    DashboardFilter,
    DashboardRepository,
    DashboardSummary,
    OperatorSummary,
)


class SqliteDashboardRepository(DashboardRepository):
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def summary(self, filters: DashboardFilter) -> DashboardSummary:
        return await asyncio.to_thread(self._summary, filters)

    async def operators(self, filters: DashboardFilter) -> list[OperatorSummary]:
        return await asyncio.to_thread(self._operators, filters)

    async def list_calls(self, request: CallPageRequest) -> CallPage:
        return await asyncio.to_thread(self._list_calls, request)

    async def processing_counts(self) -> dict[str, int]:
        return await asyncio.to_thread(self._processing_counts)

    def _summary(self, filters: DashboardFilter) -> DashboardSummary:
        where, parameters = _where(filters)
        with self._database.connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS total_calls,
                       COALESCE(SUM(CASE WHEN r.question_resolved = 'yes' THEN 1 ELSE 0 END), 0)
                           AS resolved_calls,
                       COALESCE(AVG(c.duration_seconds), 0.0) AS average_duration_seconds,
                       COALESCE(SUM(r.attention_required), 0) AS attention_calls,
                       COALESCE(SUM(CASE WHEN r.satisfaction = 'satisfied' THEN 1 ELSE 0 END), 0)
                           AS satisfied_calls,
                       COALESCE(SUM(CASE WHEN r.satisfaction = 'neutral' THEN 1 ELSE 0 END), 0)
                           AS neutral_calls,
                       COALESCE(SUM(CASE WHEN r.satisfaction = 'dissatisfied' THEN 1 ELSE 0 END), 0)
                           AS dissatisfied_calls,
                       COALESCE(SUM(CASE WHEN r.question_resolved = 'partial' THEN 1 ELSE 0 END), 0)
                           AS partially_resolved_calls,
                       COALESCE(SUM(CASE WHEN r.question_resolved = 'no' THEN 1 ELSE 0 END), 0)
                           AS unresolved_calls,
                       COALESCE(SUM(CASE WHEN r.question_resolved NOT IN ('yes', 'partial', 'no')
                           THEN 1 ELSE 0 END), 0) AS unknown_resolution_calls
                FROM calls c
                JOIN reports r ON r.call_id = c.call_id
                WHERE {where}
                """,
                parameters,
            ).fetchone()
        assert row is not None
        return DashboardSummary(
            total_calls=int(row["total_calls"]),
            resolved_calls=int(row["resolved_calls"]),
            average_duration_seconds=float(row["average_duration_seconds"]),
            attention_calls=int(row["attention_calls"]),
            satisfaction={
                "satisfied": int(row["satisfied_calls"]),
                "neutral": int(row["neutral_calls"]),
                "dissatisfied": int(row["dissatisfied_calls"]),
            },
            resolution={
                "yes": int(row["resolved_calls"]),
                "partial": int(row["partially_resolved_calls"]),
                "no": int(row["unresolved_calls"]),
                "unknown": int(row["unknown_resolution_calls"]),
            },
        )

    def _operators(self, filters: DashboardFilter) -> list[OperatorSummary]:
        where, parameters = _where(filters)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT c.operator_id, c.operator_extension, c.operator_name,
                       COUNT(*) AS total_calls,
                       CAST(ROUND(
                           100.0 * SUM(CASE WHEN r.satisfaction = 'satisfied' THEN 1 ELSE 0 END)
                           / COUNT(*)
                       ) AS INTEGER) AS satisfied_percent,
                       CAST(ROUND(
                           100.0 * SUM(CASE WHEN r.question_resolved = 'yes' THEN 1 ELSE 0 END)
                           / COUNT(*)
                       ) AS INTEGER) AS resolved_percent,
                       SUM(r.attention_required) AS attention_calls
                FROM calls c
                JOIN reports r ON r.call_id = c.call_id
                WHERE {where}
                GROUP BY c.operator_id, c.operator_extension, c.operator_name
                ORDER BY resolved_percent DESC, c.operator_name, c.operator_id
                """,
                parameters,
            ).fetchall()
        return [_operator_from_row(row) for row in rows]

    def _list_calls(self, request: CallPageRequest) -> CallPage:
        where, parameters = _where(request.filters)
        offset = (request.page - 1) * request.page_size
        direction = "ASC" if request.sort == "asc" else "DESC"
        with self._database.connect() as connection:
            total_row = connection.execute(
                f"""
                SELECT COUNT(*) AS total_items
                FROM calls c
                JOIN reports r ON r.call_id = c.call_id
                WHERE {where}
                """,
                parameters,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT c.call_id, c.recording_filenames_json, c.started_at,
                       c.duration_seconds, c.caller_id, c.caller_name,
                       c.operator_id, c.operator_extension, c.operator_name,
                       r.summary, r.satisfaction, r.question_resolved
                FROM calls c
                JOIN reports r ON r.call_id = c.call_id
                WHERE {where}
                ORDER BY c.started_at {direction}, c.call_id {direction}
                LIMIT ? OFFSET ?
                """,
                (*parameters, request.page_size, offset),
            ).fetchall()
        assert total_row is not None
        return CallPage(
            items=[_call_from_row(row) for row in rows],
            page=request.page,
            page_size=request.page_size,
            total_items=int(total_row["total_items"]),
        )

    def _processing_counts(self) -> dict[str, int]:
        counts = {
            "pending": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
            "skipped_empty": 0,
        }
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM calls GROUP BY status"
            ).fetchall()
        for row in rows:
            counts[str(row["status"])] = int(row["count"])
        return counts


def _where(filters: DashboardFilter) -> tuple[str, list[object]]:
    clauses = ["c.status = 'done'", "c.started_at >= ?", "c.started_at <= ?"]
    parameters: list[object] = [filters.date_from.isoformat(), filters.date_to.isoformat()]
    if filters.operator_extension:
        clauses.append("c.operator_extension = ?")
        parameters.append(filters.operator_extension)
    if filters.satisfaction:
        clauses.append("r.satisfaction = ?")
        parameters.append(filters.satisfaction)
    if filters.question_resolved:
        clauses.append("r.question_resolved = ?")
        parameters.append(filters.question_resolved)
    query = filters.query.strip()
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        clauses.append(
            "("
            "c.call_id LIKE ? ESCAPE '\\' OR "
            "c.caller_id LIKE ? ESCAPE '\\' OR "
            "c.caller_name LIKE ? ESCAPE '\\' OR "
            "c.operator_name LIKE ? ESCAPE '\\' OR "
            "r.summary LIKE ? ESCAPE '\\'"
            ")"
        )
        parameters.extend([pattern] * 5)
    return " AND ".join(clauses), parameters


def _operator_from_row(row: sqlite3.Row) -> OperatorSummary:
    if row["operator_id"] is None:
        raise ValueError("done call has no operator id")
    return OperatorSummary(
        id=int(row["operator_id"]),
        extension=str(row["operator_extension"]),
        name=str(row["operator_name"]),
        total_calls=int(row["total_calls"]),
        satisfied_percent=int(row["satisfied_percent"]),
        resolved_percent=int(row["resolved_percent"]),
        attention_calls=int(row["attention_calls"]),
    )


def _call_from_row(row: sqlite3.Row) -> CallListItem:
    if row["operator_id"] is None:
        raise ValueError("done call has no operator id")
    return CallListItem(
        call_id=str(row["call_id"]),
        recording_filenames=tuple(
            str(item) for item in json.loads(row["recording_filenames_json"])
        ),
        started_at=datetime.fromisoformat(str(row["started_at"])),
        duration_seconds=float(row["duration_seconds"]),
        caller_id=str(row["caller_id"]) if row["caller_id"] is not None else None,
        caller_name=str(row["caller_name"]) if row["caller_name"] is not None else None,
        operator_id=int(row["operator_id"]),
        operator_extension=str(row["operator_extension"]),
        operator_name=str(row["operator_name"]),
        summary=str(row["summary"]),
        satisfaction=str(row["satisfaction"]),
        question_resolved=str(row["question_resolved"]),
    )


__all__ = ["SqliteDashboardRepository"]
