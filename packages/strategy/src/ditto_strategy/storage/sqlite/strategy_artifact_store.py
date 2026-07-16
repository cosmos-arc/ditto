"""
SQLite-backed StrategyArtifact Reader / Writer.

Implements StrategyArtifactReaderProtocol and StrategyArtifactWriterProtocol
using SQLitePool for direct SQL access.  Uses orjson for serializing metadata
(dict) to a JSON TEXT column.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import orjson
from ditto_platform.foundation import SQLitePool, logger, traced

from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

__all__ = [
    "SQLiteStrategyArtifactReader",
    "SQLiteStrategyArtifactWriter",
]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS strategy_artifact (
    artifact_id   TEXT PRIMARY KEY,
    strategy_id   TEXT    NOT NULL,
    run_id        TEXT    NOT NULL,
    artifact_type TEXT    NOT NULL,
    file_path     TEXT    NOT NULL DEFAULT '',
    metadata      TEXT    NOT NULL DEFAULT '{}',
    status        TEXT    NOT NULL DEFAULT 'active',
    created_at    TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_STRATEGY_ID = (
    "CREATE INDEX IF NOT EXISTS idx_artifact_strategy_id "
    "ON strategy_artifact(strategy_id);"
)

_CREATE_INDEX_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_artifact_status ON strategy_artifact(status);"
)

_INSERT_IF_ABSENT_SQL = """
INSERT OR IGNORE INTO strategy_artifact (
    artifact_id, strategy_id, run_id, artifact_type,
    file_path, metadata, status, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_SQL = """
SELECT artifact_id, strategy_id, run_id, artifact_type,
       file_path, metadata, status, created_at
FROM strategy_artifact
WHERE artifact_id = ?
"""

_LIST_ALL_SQL = """
SELECT artifact_id, strategy_id, run_id, artifact_type,
       file_path, metadata, status, created_at
FROM strategy_artifact
ORDER BY created_at DESC
"""

_LIST_BY_STRATEGY_SQL = """
SELECT artifact_id, strategy_id, run_id, artifact_type,
       file_path, metadata, status, created_at
FROM strategy_artifact
WHERE strategy_id = ?
ORDER BY created_at DESC
"""

_UPDATE_STATUS_SQL = "UPDATE strategy_artifact SET status = ? WHERE artifact_id = ?"

_GET_LIFECYCLE_SQL = """
SELECT strategy_id, run_id, artifact_type, status
FROM strategy_artifact
WHERE artifact_id = ?
"""

_LIST_STATUS_BY_IDENTITY_SQL = """
SELECT artifact_id
FROM strategy_artifact
WHERE strategy_id = ? AND run_id = ? AND artifact_type = ? AND status = ?
ORDER BY artifact_id
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_record(row: sqlite3.Row) -> StrategyArtifactRecord:
    """Convert a sqlite3.Row-like object to StrategyArtifactRecord."""
    d: dict[str, Any] = dict(row)
    return StrategyArtifactRecord(
        artifact_id=str(d["artifact_id"]),
        strategy_id=str(d["strategy_id"]),
        run_id=str(d["run_id"]),
        artifact_type=ArtifactKind(d["artifact_type"]),
        file_path=str(d["file_path"]),
        metadata=dict(orjson.loads(d["metadata"])),
        status=str(d["status"]),
        created_at=str(d["created_at"]),
    )


def _lifecycle_identity(
    conn: sqlite3.Connection,
    artifact_id: str,
) -> tuple[str, str, str, str] | None:
    row = conn.execute(_GET_LIFECYCLE_SQL, (artifact_id,)).fetchone()
    if row is None:
        return None
    return (str(row[0]), str(row[1]), str(row[2]), str(row[3]))


def _ids_with_status(
    conn: sqlite3.Connection,
    identity: tuple[str, str, str],
    status: str,
) -> list[str]:
    rows = conn.execute(
        _LIST_STATUS_BY_IDENTITY_SQL,
        (*identity, status),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _rollback_false(conn: sqlite3.Connection) -> bool:
    conn.rollback()
    return False


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class SQLiteStrategyArtifactWriter:
    """SQLite-backed writer implementing StrategyArtifactWriterProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.artifact_writer.init_schema")
    def init_schema(self) -> None:
        """Create strategy_artifact table and indexes (idempotent)."""
        conn = self._pool.get_connection()
        conn.executescript(
            _CREATE_TABLE + _CREATE_INDEX_STRATEGY_ID + _CREATE_INDEX_STATUS,
        )
        self._pool.commit()
        logger.debug(
            "strategy_artifact schema initialized",
            event="artifact_schema_init",
        )

    @traced("store.artifact_writer.save")
    def save(self, record: StrategyArtifactRecord) -> bool:
        """Insert an artifact without ever replacing prior evidence."""
        conn = self._pool.get_connection()
        cursor = conn.execute(
            _INSERT_IF_ABSENT_SQL,
            (
                record.artifact_id,
                record.strategy_id,
                record.run_id,
                record.artifact_type.value,
                record.file_path,
                orjson.dumps(record.metadata, option=orjson.OPT_NON_STR_KEYS).decode(),
                record.status,
                record.created_at,
            ),
        )
        self._pool.commit()
        logger.debug(
            "strategy_artifact saved",
            event="artifact_save",
            artifact_id=record.artifact_id,
            strategy_id=record.strategy_id,
            inserted=cursor.rowcount > 0,
        )
        return cursor.rowcount > 0

    @traced("store.artifact_writer.update_status")
    def update_status(
        self,
        artifact_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...] | None = None,
    ) -> bool:
        """Update status for a specific artifact_id. Returns True if row found."""
        conn = self._pool.get_connection()
        sql = _UPDATE_STATUS_SQL
        params: list[object] = [status, artifact_id]
        if expected_current is not None:
            placeholders = ", ".join("?" for _ in expected_current)
            sql += f" AND status IN ({placeholders})"
            params.extend(expected_current)
        cursor = conn.execute(
            sql,
            params,
        )
        self._pool.commit()
        updated = cursor.rowcount
        logger.debug(
            "strategy_artifact status updated",
            event="artifact_status_update",
            artifact_id=artifact_id,
            status=status,
            updated=updated,
        )
        return updated > 0

    @traced("store.artifact_writer.claim_replacement")
    def claim_replacement(
        self,
        candidate_artifact_id: str,
        replaced_artifact_id: str,
    ) -> bool:
        """Claim the sole replacement slot for one strategy batch."""
        conn = self._pool.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            candidate = _lifecycle_identity(conn, candidate_artifact_id)
            replaced = _lifecycle_identity(conn, replaced_artifact_id)
            if candidate is None or replaced is None:
                return _rollback_false(conn)
            identity = candidate[:3]
            if (
                candidate[3] != "staged"
                or replaced[:3] != identity
                or replaced[3] != "active"
                or _ids_with_status(conn, identity, "replacing")
            ):
                return _rollback_false(conn)
            cursor = conn.execute(
                _UPDATE_STATUS_SQL + " AND status = ?",
                ("replacing", candidate_artifact_id, "staged"),
            )
            if cursor.rowcount != 1:
                return _rollback_false(conn)
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise

    @traced("store.artifact_writer.activate_candidate")
    def activate_candidate(
        self,
        candidate_artifact_id: str,
        *,
        replaced_artifact_id: str | None = None,
    ) -> bool:
        """Atomically activate a staged candidate and optionally archive its parent."""
        conn = self._pool.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            candidate = _lifecycle_identity(conn, candidate_artifact_id)
            if candidate is None:
                return _rollback_false(conn)
            identity = candidate[:3]
            active_ids = _ids_with_status(conn, identity, "active")
            expected_status = "staged"
            if replaced_artifact_id is not None:
                expected_status = "replacing"
                if active_ids != [replaced_artifact_id]:
                    return _rollback_false(conn)
                archived = conn.execute(
                    _UPDATE_STATUS_SQL + " AND status = ?",
                    ("archived", replaced_artifact_id, "active"),
                )
                if archived.rowcount != 1:
                    return _rollback_false(conn)
            elif active_ids:
                return _rollback_false(conn)
            activated = conn.execute(
                _UPDATE_STATUS_SQL + " AND status = ?",
                ("active", candidate_artifact_id, expected_status),
            )
            if activated.rowcount != 1:
                return _rollback_false(conn)
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class SQLiteStrategyArtifactReader:
    """SQLite-backed reader implementing StrategyArtifactReaderProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.artifact_reader.get")
    def get(self, artifact_id: str) -> StrategyArtifactRecord | None:
        """Get a strategy artifact by artifact_id."""
        conn = self._pool.get_connection()
        row = conn.execute(_GET_SQL, (artifact_id,)).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    @traced("store.artifact_reader.list_all")
    def list_all(self) -> list[StrategyArtifactRecord]:
        """List all strategy artifacts ordered by created_at DESC."""
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_ALL_SQL).fetchall()
        return [_row_to_record(row) for row in rows]

    @traced("store.artifact_reader.list_by_strategy")
    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        """List all artifacts for a given strategy_id, ordered by created_at DESC."""
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_BY_STRATEGY_SQL, (strategy_id,)).fetchall()
        return [_row_to_record(row) for row in rows]
