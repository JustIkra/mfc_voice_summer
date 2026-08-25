from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_MIGRATION_1 = """
CREATE TABLE calls (
    call_id TEXT PRIMARY KEY,
    recording_acct_id TEXT UNIQUE,
    recording_filenames_json TEXT NOT NULL DEFAULT '[]',
    queue_extension TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    channel_layout TEXT,
    caller_id TEXT,
    caller_name TEXT,
    caller_name_source TEXT NOT NULL DEFAULT 'unknown',
    caller_name_confidence REAL NOT NULL DEFAULT 0.0,
    operator_id INTEGER,
    operator_extension TEXT,
    operator_name TEXT,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    completed_stages_json TEXT NOT NULL DEFAULT '[]',
    attempts_json TEXT NOT NULL DEFAULT '{}',
    last_error_kind TEXT,
    last_error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE reports (
    call_id TEXT PRIMARY KEY REFERENCES calls(call_id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL,
    satisfaction TEXT NOT NULL,
    question_resolved TEXT NOT NULL,
    client_satisfaction_score INTEGER NOT NULL,
    summary TEXT NOT NULL,
    attention_required INTEGER NOT NULL CHECK (attention_required IN (0, 1)),
    generated_at TEXT NOT NULL,
    payload_codec TEXT NOT NULL,
    payload_compressed BLOB NOT NULL
);

CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    queued_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_kind TEXT,
    error_message TEXT
);

CREATE INDEX idx_calls_started_at ON calls(started_at);
CREATE INDEX idx_calls_operator_started ON calls(operator_id, started_at);
CREATE INDEX idx_calls_status ON calls(status);
CREATE INDEX idx_calls_caller_id ON calls(caller_id);
CREATE INDEX idx_reports_satisfaction ON reports(satisfaction);
CREATE INDEX idx_reports_question_resolved ON reports(question_resolved);
CREATE INDEX idx_reports_generated_at ON reports(generated_at);
CREATE UNIQUE INDEX idx_sync_runs_one_running
ON sync_runs(status)
WHERE status = 'running';
"""


class SqliteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def migrate(self) -> None:
        with self.connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"SQLite schema version {version} is newer than supported version "
                    f"{SCHEMA_VERSION}"
                )
            if version == SCHEMA_VERSION:
                return
            if version > 0:
                self._backup(connection)
            connection.executescript(_MIGRATION_1)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _backup(self, source: sqlite3.Connection) -> None:
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        destination = backup_dir / "call-analytics.before-migration.sqlite3"
        temporary = destination.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        with sqlite3.connect(temporary) as target:
            source.backup(target)
        os.replace(temporary, destination)


__all__ = ["SCHEMA_VERSION", "SqliteDatabase"]
