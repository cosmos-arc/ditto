"""FillWriter — execution_fills 表的 DDL 与写入."""

from __future__ import annotations

from ditto_execution.models import FillRecord
from ditto_execution.storage.sqlite_client import SQLiteClient

__all__ = [
    "FILLS_DDL",
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

FILLS_DDL = (
    _CREATE_FILLS_TABLE + _CREATE_IDX_FILLS_STRATEGY_DATE + _CREATE_IDX_FILLS_INTENT
)


class FillWriter:
    """execution_fills 表的写入."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: FillRecord) -> None:
        """保存成交记录."""
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
