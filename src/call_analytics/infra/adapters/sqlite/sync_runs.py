from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime

from call_analytics.infra.adapters.sqlite.database import SqliteDatabase
from call_analytics.service.ports import SyncRunRepository, SyncStatus
from domain import Period


class SqliteSyncRunRepository(SyncRunRepository):
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def start(self, period: Period, started_at: datetime) -> int | None:
        return await asyncio.to_thread(self._start, period, started_at)

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
        await asyncio.to_thread(
            self._finish,
            run_id,
            finished_at,
            status,
            discovered,
            queued,
            skipped,
            failed,
            error_kind,
            error_message,
        )

    async def last(self) -> SyncStatus | None:
        return await asyncio.to_thread(self._last)

    def _start(self, period: Period, started_at: datetime) -> int | None:
        try:
            with self._database.connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO sync_runs (
                        window_start, window_end, started_at, status
                    ) VALUES (?, ?, ?, 'running')
                    """,
                    (period.start.isoformat(), period.end.isoformat(), started_at.isoformat()),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not return a sync run id")
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def _finish(
        self,
        run_id: int,
        finished_at: datetime,
        status: str,
        discovered: int,
        queued: int,
        skipped: int,
        failed: int,
        error_kind: str | None,
        error_message: str | None,
    ) -> None:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?, discovered_count = ?,
                    queued_count = ?, skipped_count = ?, failed_count = ?,
                    error_kind = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    finished_at.isoformat(),
                    status,
                    discovered,
                    queued,
                    skipped,
                    failed,
                    error_kind,
                    error_message,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"sync run {run_id} not found")

    def _last(self) -> SyncStatus | None:
        with self._database.connect() as connection:
            row = connection.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return SyncStatus(
            window_start=datetime.fromisoformat(str(row["window_start"])),
            window_end=datetime.fromisoformat(str(row["window_end"])),
            status=str(row["status"]),
            started_at=datetime.fromisoformat(str(row["started_at"])),
            finished_at=(
                datetime.fromisoformat(str(row["finished_at"]))
                if row["finished_at"] is not None
                else None
            ),
            discovered=int(row["discovered_count"]),
            queued=int(row["queued_count"]),
            skipped=int(row["skipped_count"]),
            failed=int(row["failed_count"]),
            error_kind=(str(row["error_kind"]) if row["error_kind"] is not None else None),
            error_message=(str(row["error_message"]) if row["error_message"] is not None else None),
        )


__all__ = ["SqliteSyncRunRepository"]
