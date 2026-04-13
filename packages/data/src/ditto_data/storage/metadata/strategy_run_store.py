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
    error_message     TEXT NOT NULL DEFAULT '',
    parent_run_id     TEXT NOT NULL DEFAULT '',
    progress_pct      REAL NOT NULL DEFAULT 0.0,
    current_step      TEXT NOT NULL DEFAULT '',
    completed_days    INTEGER NOT NULL DEFAULT 0,
    total_days        INTEGER NOT NULL DEFAULT 0,
    config_json       TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_STRATEGY_ID = (
    "CREATE INDEX IF NOT EXISTS idx_strategy_run_strategy_id "
    "ON strategy_run(strategy_id);"
)

_CREATE_INDEX_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_strategy_run_status ON strategy_run(status);"
)

_CREATE_INDEX_PARENT_RUN_ID = (
    "CREATE INDEX IF NOT EXISTS idx_strategy_run_parent_run_id "
    "ON strategy_run(parent_run_id);"
)

# ---------------------------------------------------------------------------
# Incremental migration definitions
# ---------------------------------------------------------------------------
# Each tuple: (column_name, alter_sql)
# _run_migrations() uses PRAGMA table_info to skip already-applied columns.
# ---------------------------------------------------------------------------

_MIGRATIONS: list[tuple[str, str]] = [
    # 旧库升级：parent_run_id 可能在最早期 schema 中不存在
    (
        "parent_run_id",
        "ALTER TABLE strategy_run ADD COLUMN parent_run_id TEXT NOT NULL DEFAULT ''",
    ),
    (
        "progress_pct",
        "ALTER TABLE strategy_run ADD COLUMN progress_pct REAL NOT NULL DEFAULT 0.0",
    ),
    (
        "current_step",
        "ALTER TABLE strategy_run ADD COLUMN current_step TEXT NOT NULL DEFAULT ''",
    ),
    (
        "completed_days",
        "ALTER TABLE strategy_run ADD COLUMN completed_days INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "total_days",
        "ALTER TABLE strategy_run ADD COLUMN total_days INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "config_json",
        "ALTER TABLE strategy_run ADD COLUMN config_json TEXT NOT NULL DEFAULT ''",
    ),
]

_UPSERT_SQL = """
INSERT OR REPLACE INTO strategy_run (
    run_id, strategy_id, strategy_version, mode,
    status, started_at, completed_at, error_message, parent_run_id,
    progress_pct, current_step, completed_days, total_days, config_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_SQL = """
SELECT run_id, strategy_id, strategy_version, mode,
       status, started_at, completed_at, error_message, parent_run_id,
       progress_pct, current_step, completed_days, total_days, config_json
FROM strategy_run
WHERE run_id = ?
"""

_LIST_BY_STRATEGY_SQL = """
SELECT run_id, strategy_id, strategy_version, mode,
       status, started_at, completed_at, error_message, parent_run_id,
       progress_pct, current_step, completed_days, total_days, config_json
FROM strategy_run
WHERE strategy_id = ?
ORDER BY started_at DESC, run_id DESC
"""

_UPDATE_RUNNING_SQL = """
UPDATE strategy_run
SET status = ?
WHERE run_id = ? AND status NOT IN ('cancelled', 'completed', 'failed')
"""

_UPDATE_TERMINAL_SQL = """
UPDATE strategy_run
SET status = ?, completed_at = ?, error_message = ?
WHERE run_id = ? AND status NOT IN ('cancelled', 'completed', 'failed')
"""

_UPDATE_CANCELLED_SQL = """
UPDATE strategy_run
SET status = 'cancelled', completed_at = ?
WHERE run_id = ? AND status IN ('pending', 'running')
"""

_LIST_RUNS_BASE_SQL = """
SELECT run_id, strategy_id, strategy_version, mode,
       status, started_at, completed_at, error_message, parent_run_id,
       progress_pct, current_step, completed_days, total_days, config_json
FROM strategy_run
"""

_LIST_BY_PARENT_SQL = """
SELECT run_id, strategy_id, strategy_version, mode,
       status, started_at, completed_at, error_message, parent_run_id,
       progress_pct, current_step, completed_days, total_days, config_json
FROM strategy_run
WHERE parent_run_id = ?
ORDER BY started_at ASC, run_id ASC
"""

_UPDATE_PROGRESS_SQL = """
UPDATE strategy_run
SET progress_pct = ?, current_step = ?, completed_days = ?, total_days = ?
WHERE run_id = ?
"""


def _run_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply incremental ALTER TABLE migrations (idempotent).

    Uses PRAGMA table_info to detect existing columns and skips
    already-applied migrations.
    """
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(strategy_run)").fetchall()
    }
    for col_name, alter_sql in _MIGRATIONS:
        if col_name not in existing:
            conn.execute(alter_sql)
            logger.debug(
                "Migration applied",
                event="strategy_run_migration_applied",
                column=col_name,
            )


def _init_schema(pool: SQLitePool) -> None:
    """
    Create strategy_run table, run migrations, then create indexes (idempotent).

    执行顺序：
    1. CREATE TABLE IF NOT EXISTS — 建表（新库）或跳过（旧库）
    2. _run_migrations — 补齐旧库缺失的列（parent_run_id 等）
    3. CREATE INDEX IF NOT EXISTS — 在列存在后创建索引
    """
    conn = pool.get_connection()
    conn.executescript(_CREATE_TABLE)
    _run_migrations(conn)
    conn.executescript(
        _CREATE_INDEX_STRATEGY_ID + _CREATE_INDEX_STATUS + _CREATE_INDEX_PARENT_RUN_ID,
    )
    pool.commit()
    logger.debug(
        "strategy_run schema initialized",
        event="strategy_run_schema_init",
    )


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
        error_message=str(data.get("error_message", "")),
        parent_run_id=str(data.get("parent_run_id", "")),
        progress_pct=float(data.get("progress_pct", 0.0)),
        current_step=str(data.get("current_step", "")),
        completed_days=int(data.get("completed_days", 0)),
        total_days=int(data.get("total_days", 0)),
        config_json=str(data.get("config_json", "")),
    )


class SQLiteStrategyRunWriter:
    """SQLite-backed writer implementing StrategyRunWriterProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.strategy_run_writer.init_schema")
    def init_schema(self) -> None:
        """Create strategy_run table + indexes (idempotent)."""
        _init_schema(self._pool)

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
                record.parent_run_id,
                record.progress_pct,
                record.current_step,
                record.completed_days,
                record.total_days,
                record.config_json,
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
        if status == "cancelled":
            cursor = conn.execute(
                _UPDATE_CANCELLED_SQL,
                (_utc_now(), run_id),
            )
        elif status in ("completed", "failed"):
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

    @traced("store.strategy_run_writer.update_progress")
    def update_progress(
        self,
        run_id: str,
        *,
        progress_pct: float = 0.0,
        current_step: str = "",
        completed_days: int = 0,
        total_days: int = 0,
    ) -> bool:
        """Update run progress fields. Returns True if found."""
        conn = self._pool.get_connection()
        cursor = conn.execute(
            _UPDATE_PROGRESS_SQL,
            (progress_pct, current_step, completed_days, total_days, run_id),
        )
        self._pool.commit()
        updated = cursor.rowcount
        logger.debug(
            "strategy_run progress updated",
            event="strategy_run_progress_update",
            run_id=run_id,
            progress_pct=progress_pct,
            current_step=current_step,
            updated=updated,
        )
        return updated > 0


class SQLiteStrategyRunReader:
    """SQLite-backed reader implementing StrategyRunReaderProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.strategy_run_reader.init_schema")
    def init_schema(self) -> None:
        """Create strategy_run table + indexes (idempotent)."""
        _init_schema(self._pool)

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

    @traced("store.strategy_run_reader.list_runs")
    def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StrategyRunRecord]:
        """跨策略运行记录查询，支持多维度过滤与分页."""
        conditions: list[str] = []
        params: list[str | int] = []

        if strategy_id is not None:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if start_date is not None:
            conditions.append("started_at >= ?")
            params.append(start_date)
        if end_date is not None:
            conditions.append("started_at <= ?")
            params.append(end_date)

        where = ""
        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        sql = _LIST_RUNS_BASE_SQL + where + " ORDER BY started_at DESC, run_id DESC"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset is not None and limit is not None:
            sql += " OFFSET ?"
            params.append(offset)

        conn = self._pool.get_connection()
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(row) for row in rows]

    @traced("store.strategy_run_reader.list_by_parent")
    def list_by_parent(self, parent_run_id: str) -> list[StrategyRunRecord]:
        """列出指定运行的所有重放记录."""
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_BY_PARENT_SQL, (parent_run_id,)).fetchall()
        return [_row_to_record(row) for row in rows]


def _utc_now() -> str:
    """Return RFC3339 UTC timestamp."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
