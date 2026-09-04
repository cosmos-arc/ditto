"""SQLite append-only persistence for immutable industry-rotation snapshots."""

from __future__ import annotations

from ditto_platform.foundation import SQLitePool, traced

from ditto_strategy.errors import StrategySpecError
from ditto_strategy.industry_rotation.codec import (
    decode_industry_rotation,
    encode_industry_rotation,
)
from ditto_strategy.industry_rotation.contracts import IndustryRotationSnapshot

__all__ = ["SQLiteIndustryRotationStore"]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS industry_rotation_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""
_INSERT = """
INSERT INTO industry_rotation_snapshot (snapshot_id, as_of, payload_json)
VALUES (?, ?, ?)
ON CONFLICT(snapshot_id) DO NOTHING
"""
_GET = "SELECT payload_json FROM industry_rotation_snapshot WHERE snapshot_id = ?"


class SQLiteIndustryRotationStore:
    """Content-addressed store implementing exact rotation read/write ports."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.industry_rotation.init_schema")
    def init_schema(self) -> None:
        """Create the immutable snapshot table."""
        self._pool.get_connection().executescript(_CREATE_TABLE)
        self._pool.commit()

    @traced("store.industry_rotation.save")
    def save_rotation(self, value: IndustryRotationSnapshot) -> None:
        """Insert exact evidence, making an exact replay a verified no-op."""
        encoded = encode_industry_rotation(value).decode()
        connection = self._pool.get_connection()
        connection.execute(
            _INSERT,
            (value.snapshot_id, value.as_of.isoformat(), encoded),
        )
        row = connection.execute(_GET, (value.snapshot_id,)).fetchone()
        if row is None or str(row["payload_json"]) != encoded:
            self._pool.rollback()
            raise StrategySpecError(
                "industry rotation identity already owns different evidence",
                details={
                    "reason": "industry_rotation_identity_conflict",
                    "snapshot_id": value.snapshot_id,
                },
            )
        self._pool.commit()

    @traced("store.industry_rotation.get")
    def get_rotation(self, snapshot_id: str) -> IndustryRotationSnapshot | None:
        """Read and authenticate one exact snapshot."""
        row = self._pool.get_connection().execute(_GET, (snapshot_id,)).fetchone()
        if row is None:
            return None
        return decode_industry_rotation(
            str(row["payload_json"]),
            expected_snapshot_id=snapshot_id,
        )
