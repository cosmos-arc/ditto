"""SQLite readers and writers for execution position snapshots."""

from __future__ import annotations

from typing import Any

from ditto_execution.models import PositionRecord
from ditto_execution.storage.sqlite.trade._sql import build_where_clause
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient

__all__ = [
    "POSITIONS_DDL",
    "PositionReader",
    "PositionWriter",
]

_CREATE_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS actual_positions (
    snapshot_id       TEXT PRIMARY KEY,
    strategy_id       TEXT    NOT NULL,
    snapshot_date     TEXT    NOT NULL,
    instrument_id     INTEGER NOT NULL,
    quantity          INTEGER NOT NULL,
    available_quantity INTEGER NOT NULL,
    average_cost      REAL    NOT NULL,
    market_value      REAL    NOT NULL,
    unrealized_pnl    REAL    NOT NULL,
    realized_pnl      REAL    NOT NULL,
    total_fees        REAL    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_POSITIONS_STRATEGY_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_actual_positions_strategy_date "
    "ON actual_positions(strategy_id, snapshot_date);"
)

_CREATE_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_actual_positions_strategy_instrument_date "
    "ON actual_positions(strategy_id, instrument_id, snapshot_date);"
)

_INSERT_POSITION = """
INSERT OR REPLACE INTO actual_positions
    (snapshot_id, strategy_id, snapshot_date, instrument_id, quantity,
     available_quantity, average_cost, market_value, unrealized_pnl,
     realized_pnl, total_fees, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_LATEST_POSITION = """
SELECT * FROM actual_positions
WHERE strategy_id = ? AND instrument_id = ?
ORDER BY snapshot_date DESC
LIMIT 1
"""

_LIST_POSITIONS_BASE = "SELECT * FROM actual_positions WHERE strategy_id = ?"

POSITIONS_DDL = (
    _CREATE_POSITIONS_TABLE
    + _CREATE_IDX_POSITIONS_STRATEGY_DATE
    + _CREATE_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE
)


class PositionReader:
    """Read execution position snapshots from the ``actual_positions`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get_latest(self, strategy_id: str, instrument_id: int) -> PositionRecord | None:
        """Return the latest position snapshot for one strategy and instrument."""
        row = self._client.fetchone(_GET_LATEST_POSITION, (strategy_id, instrument_id))
        return self._row_to_position(row) if row else None

    def list(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
    ) -> list[PositionRecord]:
        """Return position snapshots matching the requested filters."""
        sql, params = build_where_clause(
            _LIST_POSITIONS_BASE,
            strategy_id,
            {"snapshot_date": snapshot_date},
            "snapshot_date ASC",
        )
        rows = self._client.fetchall(sql, params)
        return [self._row_to_position(row) for row in rows]

    @staticmethod
    def _row_to_position(row: dict[str, Any]) -> PositionRecord:
        return PositionRecord(**row)


class PositionWriter:
    """Write execution position snapshots to the ``actual_positions`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: PositionRecord) -> None:
        """Persist a position snapshot."""
        self._client.execute(
            _INSERT_POSITION,
            (
                record.snapshot_id,
                record.strategy_id,
                record.snapshot_date,
                record.instrument_id,
                record.quantity,
                record.available_quantity,
                record.average_cost,
                record.market_value,
                record.unrealized_pnl,
                record.realized_pnl,
                record.total_fees,
                record.created_at,
            ),
        )
        self._client.commit()
