"""SQLite readers and writers for execution position snapshots."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import SQLiteClient

from ditto_execution.models import PositionRecord
from ditto_execution.storage.sqlite.trade._sql import build_where_clause

__all__ = [
    "POSITIONS_DDL",
    "PositionReader",
    "PositionWriter",
]

_CREATE_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS actual_positions (
    snapshot_id       TEXT PRIMARY KEY,
    run_id            TEXT    NOT NULL DEFAULT '',
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
    "CREATE UNIQUE INDEX IF NOT EXISTS "
    "idx_actual_positions_run_strategy_instrument_date "
    "ON actual_positions(run_id, strategy_id, instrument_id, snapshot_date);"
)

_DROP_LEGACY_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE = (
    "DROP INDEX IF EXISTS idx_actual_positions_strategy_instrument_date;"
)

_CREATE_IDX_POSITIONS_RUN_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_actual_positions_run_date "
    "ON actual_positions(run_id, snapshot_date);"
)

_INSERT_POSITION = """
INSERT OR REPLACE INTO actual_positions
    (snapshot_id, run_id, strategy_id, snapshot_date, instrument_id, quantity,
     available_quantity, average_cost, market_value, unrealized_pnl,
     realized_pnl, total_fees, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_LATEST_POSITION = """
SELECT * FROM actual_positions
WHERE strategy_id = ? AND instrument_id = ?
  AND (? IS NULL OR run_id = ?)
ORDER BY snapshot_date DESC
LIMIT 1
"""

_LIST_POSITIONS_BASE = "SELECT * FROM actual_positions WHERE strategy_id = ?"

POSITIONS_DDL = _CREATE_POSITIONS_TABLE + _CREATE_IDX_POSITIONS_STRATEGY_DATE


def ensure_position_schema(client: SQLiteClient) -> None:
    """Ensure the actual_positions table carries current run-scoped identity."""
    client.execute(_CREATE_POSITIONS_TABLE)
    columns = {
        str(row["name"])
        for row in client.fetchall("PRAGMA table_info(actual_positions)")
    }
    if "run_id" not in columns:
        client.execute(
            "ALTER TABLE actual_positions ADD COLUMN run_id TEXT NOT NULL DEFAULT ''"
        )
    client.execute(_DROP_LEGACY_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE)
    client.execute(_CREATE_IDX_POSITIONS_STRATEGY_DATE)
    client.execute(_CREATE_IDX_POSITIONS_RUN_DATE)
    client.execute(_CREATE_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE)
    client.commit()


class PositionReader:
    """Read execution position snapshots from the ``actual_positions`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        ensure_position_schema(self._client)

    def get_latest(
        self,
        strategy_id: str,
        instrument_id: int,
        run_id: str | None = None,
    ) -> PositionRecord | None:
        """Return the latest position snapshot for one strategy and instrument."""
        row = self._client.fetchone(
            _GET_LATEST_POSITION, (strategy_id, instrument_id, run_id, run_id)
        )
        return self._row_to_position(row) if row else None

    def list(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
        run_id: str | None = None,
    ) -> list[PositionRecord]:
        """Return position snapshots matching the requested filters."""
        sql, params = build_where_clause(
            _LIST_POSITIONS_BASE,
            strategy_id,
            {"snapshot_date": snapshot_date, "run_id": run_id},
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
        ensure_position_schema(self._client)

    def save(self, record: PositionRecord) -> None:
        """Persist a position snapshot."""
        self._client.execute(
            _INSERT_POSITION,
            (
                record.snapshot_id,
                record.run_id,
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
