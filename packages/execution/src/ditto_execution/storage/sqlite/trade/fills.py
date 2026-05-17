"""SQLite readers and writers for execution fills."""

from __future__ import annotations

from typing import Any

from ditto_execution.models import FillRecord
from ditto_execution.storage.sqlite.trade._sql import build_where_clause
from ditto_platform.foundation import SQLiteClient

__all__ = [
    "FILLS_DDL",
    "FillReader",
    "FillWriter",
]

_CREATE_FILLS_TABLE = """
CREATE TABLE IF NOT EXISTS execution_fills (
    fill_id        TEXT PRIMARY KEY,
    intent_id      TEXT    NOT NULL,
    strategy_id    TEXT    NOT NULL,
    trade_date     TEXT    NOT NULL,
    instrument_id  INTEGER NOT NULL,
    direction      TEXT    NOT NULL,
    quantity       INTEGER NOT NULL,
    fill_price     REAL    NOT NULL,
    fee            REAL    NOT NULL,
    slippage       REAL    NOT NULL DEFAULT 0.0,
    notes          TEXT    NOT NULL DEFAULT '',
    settlement_date TEXT   NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_FILLS_STRATEGY_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_execution_fills_strategy_date "
    "ON execution_fills(strategy_id, trade_date);"
)

_CREATE_IDX_FILLS_INTENT = (
    "CREATE INDEX IF NOT EXISTS idx_execution_fills_intent "
    "ON execution_fills(intent_id);"
)

_INSERT_FILL = """
INSERT OR IGNORE INTO execution_fills
    (fill_id, intent_id, strategy_id, trade_date, instrument_id, direction,
     quantity, fill_price, fee, slippage, notes, settlement_date, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_FILL_BY_ID = "SELECT * FROM execution_fills WHERE fill_id = ?"

_FIND_FILL_BY_INTENT_AND_DATE = (
    "SELECT * FROM execution_fills WHERE intent_id = ? AND trade_date = ? LIMIT 1"
)

_LIST_FILLS_BASE = "SELECT * FROM execution_fills WHERE strategy_id = ?"

FILLS_DDL = (
    _CREATE_FILLS_TABLE + _CREATE_IDX_FILLS_STRATEGY_DATE + _CREATE_IDX_FILLS_INTENT
)


class FillReader:
    """Read fill records from the ``execution_fills`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get(self, fill_id: str) -> FillRecord | None:
        """Return one fill by ID."""
        row = self._client.fetchone(_SELECT_FILL_BY_ID, (fill_id,))
        return self._row_to_fill(row) if row else None

    def find(self, intent_id: str, trade_date: str) -> FillRecord | None:
        """Find a fill by intent ID and trade date for idempotency."""
        row = self._client.fetchone(
            _FIND_FILL_BY_INTENT_AND_DATE, (intent_id, trade_date)
        )
        return self._row_to_fill(row) if row else None

    def list(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        """Return fill records matching the requested filters."""
        filters: dict[str, str | tuple[str, str] | None] = {}

        if trade_date is not None and end_date is not None:
            filters["trade_date"] = (trade_date, end_date)
        elif trade_date is not None:
            filters["trade_date"] = trade_date
        elif end_date is not None:
            filters["trade_date"] = ("", end_date)

        if intent_id is not None:
            filters["intent_id"] = intent_id

        sql, params = build_where_clause(
            _LIST_FILLS_BASE, strategy_id, filters, "trade_date ASC"
        )

        rows = self._client.fetchall(sql, params)
        return [self._row_to_fill(row) for row in rows]

    @staticmethod
    def _row_to_fill(row: dict[str, Any]) -> FillRecord:
        return FillRecord(**row)


class FillWriter:
    """Write fill records to the ``execution_fills`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: FillRecord) -> None:
        """Persist a fill record."""
        self._client.execute(
            _INSERT_FILL,
            (
                record.fill_id,
                record.intent_id,
                record.strategy_id,
                record.trade_date,
                record.instrument_id,
                record.direction,
                record.quantity,
                record.fill_price,
                record.fee,
                record.slippage,
                record.notes,
                record.settlement_date,
                record.created_at,
            ),
        )
        self._client.commit()
