"""SQLite schema, reader, and writer for append-only fill adjustments."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import SQLiteClient

from ditto_execution.models import FillAdjustmentRecord

__all__ = [
    "FILL_ADJUSTMENTS_DDL",
    "FillAdjustmentReader",
    "FillAdjustmentWriter",
]

_CREATE_FILL_ADJUSTMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS execution_fill_adjustments (
    adjustment_id       TEXT PRIMARY KEY,
    fill_id             TEXT NOT NULL,
    adjustment_type     TEXT NOT NULL CHECK (adjustment_type IN ('void', 'replace')),
    replacement_fill_id TEXT NULL,
    reason              TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at          TEXT NOT NULL,
    CHECK (
        (adjustment_type = 'void' AND replacement_fill_id IS NULL)
        OR
        (adjustment_type = 'replace' AND replacement_fill_id IS NOT NULL)
    )
);
"""

_CREATE_IDX_FILL_ADJUSTMENTS_FILL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_fill_adjustments_fill "
    "ON execution_fill_adjustments(fill_id);"
)

FILL_ADJUSTMENTS_DDL = (
    _CREATE_FILL_ADJUSTMENTS_TABLE + _CREATE_IDX_FILL_ADJUSTMENTS_FILL
)

_INSERT_FILL_ADJUSTMENT = """
INSERT INTO execution_fill_adjustments
    (adjustment_id, fill_id, adjustment_type, replacement_fill_id, reason, created_at)
VALUES (?, ?, ?, ?, ?, ?)
"""

_SELECT_FILL_ADJUSTMENT_BY_ID = (
    "SELECT * FROM execution_fill_adjustments WHERE adjustment_id = ?"
)

_SELECT_FILL_ADJUSTMENT_BY_FILL = (
    "SELECT * FROM execution_fill_adjustments WHERE fill_id = ?"
)


class FillAdjustmentReader:
    """Read append-only fill correction events."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get(self, adjustment_id: str) -> FillAdjustmentRecord | None:
        """Return one adjustment by its idempotency key."""
        row = self._client.fetchone(
            _SELECT_FILL_ADJUSTMENT_BY_ID,
            (adjustment_id,),
        )
        return self._row_to_adjustment(row) if row else None

    def get_for_fill(self, fill_id: str) -> FillAdjustmentRecord | None:
        """Return the unique adjustment targeting a fill, when present."""
        row = self._client.fetchone(
            _SELECT_FILL_ADJUSTMENT_BY_FILL,
            (fill_id,),
        )
        return self._row_to_adjustment(row) if row else None

    def list(
        self,
        strategy_id: str,
        *,
        fill_id: str | None = None,
        intent_id: str | None = None,
    ) -> list[FillAdjustmentRecord]:
        """List adjustment evidence joined through immutable source fills."""
        clauses = ["f.strategy_id = ?"]
        params: list[object] = [strategy_id]
        if fill_id is not None:
            clauses.append("a.fill_id = ?")
            params.append(fill_id)
        if intent_id is not None:
            clauses.append("f.intent_id = ?")
            params.append(intent_id)
        sql = (
            "SELECT a.* FROM execution_fill_adjustments AS a "  # noqa: S608
            "JOIN execution_fills AS f ON f.fill_id = a.fill_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY a.created_at ASC, a.adjustment_id ASC"
        )
        rows = self._client.fetchall(sql, tuple(params))
        return [self._row_to_adjustment(row) for row in rows]

    @staticmethod
    def _row_to_adjustment(row: dict[str, Any]) -> FillAdjustmentRecord:
        return FillAdjustmentRecord(**row)


class FillAdjustmentWriter:
    """Append fill correction events without exposing mutation methods."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save_uncommitted(self, record: FillAdjustmentRecord) -> None:
        """Append one adjustment in the caller-owned transaction."""
        self._client.execute(
            _INSERT_FILL_ADJUSTMENT,
            (
                record.adjustment_id,
                record.fill_id,
                record.adjustment_type,
                record.replacement_fill_id,
                record.reason,
                record.created_at,
            ),
        )
