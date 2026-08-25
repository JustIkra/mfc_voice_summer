from __future__ import annotations

from pathlib import Path

from call_analytics.infra.adapters.sqlite import SqliteDatabase


def test_database_migration_creates_three_tables_and_indexes(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "calls.sqlite3")

    database.migrate()

    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        indexes = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert {"calls", "reports", "sync_runs"} <= tables
    assert "idx_sync_runs_one_running" in indexes
    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert user_version == 1


def test_database_rejects_newer_unknown_schema(tmp_path: Path) -> None:
    database = SqliteDatabase(tmp_path / "calls.sqlite3")
    with database.connect() as connection:
        connection.execute("PRAGMA user_version = 99")

    try:
        database.migrate()
    except RuntimeError as error:
        assert str(error) == "SQLite schema version 99 is newer than supported version 1"
    else:
        raise AssertionError("newer schema must be rejected")
