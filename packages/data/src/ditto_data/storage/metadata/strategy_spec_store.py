"""
SQLite-backed StrategySpec Reader / Writer.

Implements StrategySpecReaderProtocol and StrategySpecWriterProtocol using
SQLitePool for direct SQL access.  Uses orjson for serializing spec_json
(dict) and tags (tuple[str, ...]) to JSON TEXT columns.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import orjson
from ditto_platform.foundation import SQLitePool, logger, traced

from ditto_data.models.strategy import StrategySpecRecord

__all__ = [
    "SQLiteStrategySpecReader",
    "SQLiteStrategySpecWriter",
]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS strategy_spec (
    strategy_id TEXT NOT NULL,
    version     INT  NOT NULL,
    name        TEXT NOT NULL,
    spec_json   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',
    tags        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (strategy_id, version)
);
"""

_CREATE_INDEX_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_spec_status ON strategy_spec(status);"
)

_CREATE_INDEX_STRATEGY_ID = (
    "CREATE INDEX IF NOT EXISTS idx_spec_strategy_id ON strategy_spec(strategy_id);"
)

_UPSERT_SQL = """
INSERT OR REPLACE INTO strategy_spec (
    strategy_id, version, name, spec_json, status, tags,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_BY_VERSION_SQL = """
SELECT strategy_id, version, name, spec_json, status, tags,
       created_at, updated_at
FROM strategy_spec
WHERE strategy_id = ? AND version = ?
"""

_GET_LATEST_SQL = """
SELECT strategy_id, version, name, spec_json, status, tags,
       created_at, updated_at
FROM strategy_spec
WHERE strategy_id = ?
ORDER BY version DESC
LIMIT 1
"""

_LIST_ALL_LATEST_SQL = """
SELECT s.strategy_id, s.version, s.name, s.spec_json, s.status, s.tags,
       s.created_at, s.updated_at
FROM strategy_spec s
INNER JOIN (
    SELECT strategy_id, MAX(version) AS max_ver
    FROM strategy_spec
    GROUP BY strategy_id
) latest ON s.strategy_id = latest.strategy_id AND s.version = latest.max_ver
"""

_LIST_VERSIONS_SQL = """
SELECT strategy_id, version, name, spec_json, status, tags,
       created_at, updated_at
FROM strategy_spec
WHERE strategy_id = ?
ORDER BY version DESC
"""

_UPDATE_STATUS_SQL = """
UPDATE strategy_spec
SET status = ?
WHERE strategy_id = ? AND version = ?
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_record(row: sqlite3.Row) -> StrategySpecRecord:
    """Convert a sqlite3.Row-like object to StrategySpecRecord."""
    d: dict[str, Any] = dict(row)
    return StrategySpecRecord(
        strategy_id=str(d["strategy_id"]),
        name=str(d["name"]),
        spec_json=dict(orjson.loads(d["spec_json"])),
        version=int(d["version"]),
        status=str(d["status"]),
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
        tags=tuple(orjson.loads(d["tags"])),
    )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class SQLiteStrategySpecWriter:
    """SQLite-backed writer implementing StrategySpecWriterProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.spec_writer.init_schema")
    def init_schema(self) -> None:
        """Create strategy_spec table and indexes (idempotent)."""
        conn = self._pool.get_connection()
        conn.executescript(
            _CREATE_TABLE + _CREATE_INDEX_STATUS + _CREATE_INDEX_STRATEGY_ID,
        )
        self._pool.commit()
        logger.debug(
            "strategy_spec schema initialized",
            event="spec_schema_init",
        )

    @traced("store.spec_writer.save")
    def save(self, record: StrategySpecRecord) -> None:
        """INSERT OR REPLACE a StrategySpecRecord."""
        conn = self._pool.get_connection()
        conn.execute(
            _UPSERT_SQL,
            (
                record.strategy_id,
                record.version,
                record.name,
                orjson.dumps(record.spec_json).decode(),
                record.status,
                orjson.dumps(record.tags).decode(),
                record.created_at,
                record.updated_at,
            ),
        )
        self._pool.commit()
        logger.debug(
            "strategy_spec saved",
            event="spec_save",
            strategy_id=record.strategy_id,
            version=record.version,
        )

    @traced("store.spec_writer.update_status")
    def update_status(self, strategy_id: str, version: int, status: str) -> bool:
        """Update status for (strategy_id, version). Returns True if found."""
        conn = self._pool.get_connection()
        cursor = conn.execute(
            _UPDATE_STATUS_SQL,
            (status, strategy_id, version),
        )
        self._pool.commit()
        updated = cursor.rowcount
        logger.debug(
            "strategy_spec status updated",
            event="spec_status_update",
            strategy_id=strategy_id,
            version=version,
            status=status,
            updated=updated,
        )
        return updated > 0


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class SQLiteStrategySpecReader:
    """SQLite-backed reader implementing StrategySpecReaderProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.spec_reader.get")
    def get(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        """Get a strategy spec. version=None returns the latest version."""
        conn = self._pool.get_connection()
        if version is not None:
            row = conn.execute(_GET_BY_VERSION_SQL, (strategy_id, version)).fetchone()
        else:
            row = conn.execute(_GET_LATEST_SQL, (strategy_id,)).fetchone()

        if row is None:
            return None
        return _row_to_record(row)

    @traced("store.spec_reader.list_all")
    def list_all(self) -> list[StrategySpecRecord]:
        """List all strategy specs (latest version per strategy_id)."""
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_ALL_LATEST_SQL).fetchall()
        return [_row_to_record(row) for row in rows]

    @traced("store.spec_reader.list_versions")
    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        """List all versions for a given strategy_id, ordered by version DESC."""
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_VERSIONS_SQL, (strategy_id,)).fetchall()
        return [_row_to_record(row) for row in rows]
