"""
SQLite-backed StrategyArtifact Reader / Writer.

Implements StrategyArtifactReaderProtocol and StrategyArtifactWriterProtocol
using SQLitePool for direct SQL access.  Uses orjson for serializing metadata
(dict) to a JSON TEXT column.
"""

from typing import Any

import orjson
from ditto_infra.foundation import SQLitePool, logger, traced

from ditto_data.models.strategy import ArtifactKind, StrategyArtifactRecord

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

_UPSERT_SQL = """
INSERT OR REPLACE INTO strategy_artifact (
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

_UPDATE_STATUS_SQL = """
UPDATE strategy_artifact
SET status = ?
WHERE artifact_id = ?
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_record(row: Any) -> StrategyArtifactRecord:
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
    def save(self, record: StrategyArtifactRecord) -> None:
        """INSERT OR REPLACE a StrategyArtifactRecord."""
        conn = self._pool.get_connection()
        conn.execute(
            _UPSERT_SQL,
            (
                record.artifact_id,
                record.strategy_id,
                record.run_id,
                record.artifact_type.value,
                record.file_path,
                orjson.dumps(record.metadata).decode(),
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
        )

    @traced("store.artifact_writer.update_status")
    def update_status(self, artifact_id: str, status: str) -> bool:
        """Update status for a specific artifact_id. Returns True if row found."""
        conn = self._pool.get_connection()
        cursor = conn.execute(
            _UPDATE_STATUS_SQL,
            (status, artifact_id),
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


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class SQLiteStrategyArtifactReader:
    """SQLite-backed reader implementing StrategyArtifactReaderProtocol."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.artifact_reader.init_schema")
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
