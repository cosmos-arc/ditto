"""
SQLite-backed StrategyRun Reader / Writer.

Implements StrategyRunReaderProtocol and StrategyRunWriterProtocol using
SQLitePool for direct SQL access.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from ditto_infra.foundation import SQLitePool, logger, traced

from ditto_data.models.strategy_run import StrategyRunRecord

__all__ = [
    "SQLiteStrategyRunReader",
    "SQLiteStrategyRunWriter",
]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS strategy_run (
    run_id            TEXT PRIMARY KEY,
    strategy_id       TEXT NOT NULL,
    strategy_version  TEXT NOT NULL DEFAULT '',
    mode              TEXT NOT NULL DEFAULT 'backtest',
    status            TEXT NOT NULL DEFAULT 'pending',
    started_at        TEXT NOT NULL DEFAULT '',
    completed_at      TEXT NOT NULL DEFAULT '',
    error_message     TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_STRATEGY_ID = (
    "CREATE INDEX IF NOT EXISTS idx_strategy_run_strategy_id "
    "ON strategy_run(strategy_id);"
)

_CREATE_INDEX_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_strategy_run_status ON strategy_run(status);"
)

_UPSERT_SQL = """
INSERT OR REPLACE INTO strategy_run (
    run_id, strategy_id, strategy_version, mode,
    status, started_at, completed_at, error_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_SQL = """
SELECT run_id, strategy_id, strategy_version, mode,
       status, started_at, completed_at, error_message
FROM strategy_run
WHERE run_id = ?
"""

_LIST_BY_STRATEGY_SQL = """
SELECT run_id, strategy_id, strategy_version, mode,
       status, started_at, completed_at, error_message
FROM strategy_run
WHERE strategy_id = ?
ORDER BY started_at DESC, run_id DESC
"""

_UPDATE_RUNNING_SQL = """
UPDATE strategy_run
SET status = ?
WHERE run_id = ?
"""

_UPDATE_TERMINAL_SQL = """
UPDATE strategy_run
SET status = ?, completed_at = ?, error_message = ?
WHERE run_id = ?
"""


def _row_to_record(row: sqlite3.Row) -> StrategyRunRecord:
    """Convert a sqlite3.Row-like object to StrategyRunRecord."""
    data: dict[str, Any] = dict(row)
    return StrategyRunRecord(
        run_id=str(data["run_id"]),
        strategy_id=str(data["strategy_id"]),
        strategy_version=str(data["strategy_version"]),
        mode=str(data["mode"]),
        status=str(data["status"]),
        started_at=str(data["started_at"]),
        completed_at=str(data["completed_at"]),
        error_message=str(data["error_message"]),
    )


class SQLiteStrategyRunWriter:
    """SQLite-backed writer implementing StrategyRunWriterProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.strategy_run_writer.init_schema")
    def init_schema(self) -> None:
        """Create strategy_run table and indexes (idempotent)."""
        conn = self._pool.get_connection()
        conn.executescript(
            _CREATE_TABLE + _CREATE_INDEX_STRATEGY_ID + _CREATE_INDEX_STATUS,
        )
        self._pool.commit()
        logger.debug(
            "strategy_run schema initialized",
            event="strategy_run_schema_init",
        )

    @traced("store.strategy_run_writer.save")
    def save(self, record: StrategyRunRecord) -> None:
        """INSERT OR REPLACE a StrategyRunRecord."""
        conn = self._pool.get_connection()
        conn.execute(
            _UPSERT_SQL,
            (
                record.run_id,
                record.strategy_id,
                record.strategy_version,
                record.mode,
                record.status,
                record.started_at,
                record.completed_at,
                record.error_message,
            ),
        )
        self._pool.commit()
        logger.debug(
            "strategy_run saved",
            event="strategy_run_save",
            run_id=record.run_id,
            strategy_id=record.strategy_id,
        )

    @traced("store.strategy_run_writer.update_status")
    def update_status(
        self,
        run_id: str,
        status: str,
        error_message: str = "",
    ) -> bool:
        """Update run status and terminal metadata. Returns True if found."""
        conn = self._pool.get_connection()
        if status in ("completed", "failed"):
            cursor = conn.execute(
                _UPDATE_TERMINAL_SQL,
                (status, _utc_now(), error_message, run_id),
            )
        else:
            cursor = conn.execute(
                _UPDATE_RUNNING_SQL,
                (status, run_id),
            )
        self._pool.commit()
        updated = cursor.rowcount
        logger.debug(
            "strategy_run status updated",
            event="strategy_run_status_update",
            run_id=run_id,
            status=status,
            updated=updated,
        )
        return updated > 0


class SQLiteStrategyRunReader:
    """SQLite-backed reader implementing StrategyRunReaderProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.strategy_run_reader.init_schema")
    def init_schema(self) -> None:
        """Create strategy_run table and indexes (idempotent)."""
        conn = self._pool.get_connection()
        conn.executescript(
            _CREATE_TABLE + _CREATE_INDEX_STRATEGY_ID + _CREATE_INDEX_STATUS,
        )
        self._pool.commit()
        logger.debug(
            "strategy_run schema initialized",
            event="strategy_run_schema_init",
        )

    @traced("store.strategy_run_reader.get")
    def get(self, run_id: str) -> StrategyRunRecord | None:
        """Get a strategy run by run_id."""
        conn = self._pool.get_connection()
        row = conn.execute(_GET_SQL, (run_id,)).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    @traced("store.strategy_run_reader.list_by_strategy")
    def list_by_strategy(self, strategy_id: str) -> list[StrategyRunRecord]:
        """List all runs for a given strategy_id ordered by started_at DESC."""
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_BY_STRATEGY_SQL, (strategy_id,)).fetchall()
        return [_row_to_record(row) for row in rows]


def _utc_now() -> str:
    """Return RFC3339 UTC timestamp."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
