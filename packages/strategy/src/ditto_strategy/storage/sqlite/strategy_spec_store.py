"""
SQLite-backed StrategySpec Reader / Writer.

Implements StrategySpecReaderProtocol and StrategySpecWriterProtocol using
SQLitePool for direct SQL access.  Uses orjson for serializing spec_json
(dict) and tags (tuple[str, ...]) to JSON TEXT columns.

strategy_spec 是纯 immutable payload（无 status/updated_at 列）；状态由 governance
唯一管理。INSERT-only：重复 (strategy_id, version) 抛 IntegrityError。
"""

from __future__ import annotations

import sqlite3
from typing import Any

import orjson
from ditto_platform.foundation import SQLitePool, logger, traced

from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "SQLiteStrategySpecReader",
    "SQLiteStrategySpecWriter",
]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS strategy_spec (
    strategy_id    TEXT NOT NULL,
    version        INT  NOT NULL,
    name           TEXT NOT NULL,
    spec_json      TEXT NOT NULL,
    spec_hash      TEXT NOT NULL DEFAULT '',
    parent_version INT,
    tags           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (strategy_id, version)
);
"""

_CREATE_INDEX_HASH = (
    "CREATE INDEX IF NOT EXISTS idx_spec_hash ON strategy_spec(spec_hash);"
)

_CREATE_INDEX_STRATEGY_ID = (
    "CREATE INDEX IF NOT EXISTS idx_spec_strategy_id ON strategy_spec(strategy_id);"
)

_INSERT_SQL = """
INSERT INTO strategy_spec (
    strategy_id, version, name, spec_json, spec_hash, parent_version,
    tags, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_BY_VERSION_SQL = """
SELECT strategy_id, version, name, spec_json, spec_hash, parent_version,
       tags, created_at
FROM strategy_spec
WHERE strategy_id = ? AND version = ?
"""

_GET_LATEST_SQL = """
SELECT strategy_id, version, name, spec_json, spec_hash, parent_version,
       tags, created_at
FROM strategy_spec
WHERE strategy_id = ?
ORDER BY version DESC
LIMIT 1
"""

_LIST_ALL_LATEST_SQL = """
SELECT s.strategy_id, s.version, s.name, s.spec_json, s.spec_hash,
       s.parent_version, s.tags, s.created_at
FROM strategy_spec s
INNER JOIN (
    SELECT strategy_id, MAX(version) AS max_ver
    FROM strategy_spec
    GROUP BY strategy_id
) latest ON s.strategy_id = latest.strategy_id AND s.version = latest.max_ver
"""

_LIST_VERSIONS_SQL = """
SELECT strategy_id, version, name, spec_json, spec_hash, parent_version,
       tags, created_at
FROM strategy_spec
WHERE strategy_id = ?
ORDER BY version DESC
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
        spec_hash=str(d["spec_hash"]),
        version=int(d["version"]),
        parent_version=(
            None if d["parent_version"] is None else int(d["parent_version"])
        ),
        created_at=str(d["created_at"]),
        tags=tuple(orjson.loads(d["tags"])),
    )


def insert_spec_payload(conn: sqlite3.Connection, record: StrategySpecRecord) -> None:
    """
    INSERT one spec payload on the given connection without committing.

    Shared by :meth:`SQLiteStrategySpecWriter.save` and atomic governance
    version creation so the payload and its governance version land in one
    transaction. Duplicate (strategy_id, version) raises IntegrityError.
    """
    conn.execute(
        _INSERT_SQL,
        (
            record.strategy_id,
            record.version,
            record.name,
            orjson.dumps(record.spec_json).decode(),
            record.spec_hash,
            record.parent_version,
            orjson.dumps(record.tags).decode(),
            record.created_at,
        ),
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
            _CREATE_TABLE + _CREATE_INDEX_STRATEGY_ID + _CREATE_INDEX_HASH,
        )
        self._pool.commit()
        logger.debug(
            "strategy_spec schema initialized",
            event="spec_schema_init",
        )

    @traced("store.spec_writer.save")
    def save(self, record: StrategySpecRecord) -> None:
        """INSERT a StrategySpecRecord (append-only; duplicate PK raises)."""
        conn = self._pool.get_connection()
        insert_spec_payload(conn, record)
        self._pool.commit()
        logger.debug(
            "strategy_spec saved",
            event="spec_save",
            strategy_id=record.strategy_id,
            version=record.version,
        )


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class SQLiteStrategySpecReader:
    """SQLite-backed reader implementing StrategySpecReaderProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.spec_reader.get_spec")
    def get_spec(
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

    @traced("store.spec_reader.list_specs")
    def list_specs(self) -> list[StrategySpecRecord]:
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
