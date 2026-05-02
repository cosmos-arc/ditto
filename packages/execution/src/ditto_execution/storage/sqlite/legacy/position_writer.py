"""PositionWriter — actual_positions 表的 DDL 与写入."""

from __future__ import annotations

from ditto_execution.models import PositionRecord
from ditto_execution.storage.sqlite_client import SQLiteClient

__all__ = [
    "POSITIONS_DDL",
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

POSITIONS_DDL = (
    _CREATE_POSITIONS_TABLE
    + _CREATE_IDX_POSITIONS_STRATEGY_DATE
    + _CREATE_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE
)


class PositionWriter:
    """actual_positions 表的写入."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: PositionRecord) -> None:
        """保存持仓快照."""
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
