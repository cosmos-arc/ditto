"""SQLite readers and writers for execution trade intents."""

from __future__ import annotations

from typing import Any

from ditto_execution.models import SignalRecord
from ditto_execution.storage.sqlite.trade._sql import build_where_clause
from ditto_platform.foundation import SQLiteClient

__all__ = [
    "INTENTS_DDL",
    "IntentReader",
    "IntentWriter",
]

_CREATE_INTENTS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_intents (
    intent_id      TEXT PRIMARY KEY,
    strategy_id    TEXT    NOT NULL,
    signal_date    TEXT    NOT NULL,
    instrument_id  INTEGER NOT NULL,
    direction      TEXT    NOT NULL,
    target_weight  REAL    NOT NULL,
    current_weight REAL    NOT NULL,
    delta_weight   REAL    NOT NULL,
    quantity       INTEGER,
    status         TEXT    NOT NULL DEFAULT 'pending',
    created_at     TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_INTENTS_STRATEGY_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_trade_intents_strategy_date "
    "ON trade_intents(strategy_id, signal_date);"
)

_CREATE_IDX_INTENTS_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_trade_intents_status ON trade_intents(status);"
)

_INSERT_INTENT = """
INSERT INTO trade_intents
    (intent_id, strategy_id, signal_date, instrument_id, direction,
     target_weight, current_weight, delta_weight, quantity, status, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_INTENT_BY_ID = "SELECT * FROM trade_intents WHERE intent_id = ?"

_LIST_INTENTS_BASE = "SELECT * FROM trade_intents WHERE strategy_id = ?"

_UPDATE_INTENT_STATUS_TRANSITION = (
    "UPDATE trade_intents SET status = ? "
    "WHERE intent_id = ? AND status IN ({placeholders})"
)

INTENTS_DDL = (
    _CREATE_INTENTS_TABLE
    + _CREATE_IDX_INTENTS_STRATEGY_DATE
    + _CREATE_IDX_INTENTS_STATUS
)


class IntentReader:
    """Read trade intent records from the ``trade_intents`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get(self, intent_id: str) -> SignalRecord | None:
        """Return one trade intent by ID."""
        row = self._client.fetchone(_SELECT_INTENT_BY_ID, (intent_id,))
        return self._row_to_signal(row) if row else None

    def list(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        """Return trade intents matching the requested filters."""
        sql, params = build_where_clause(
            _LIST_INTENTS_BASE,
            strategy_id,
            {"signal_date": signal_date, "status": status},
            "signal_date ASC",
        )
        rows = self._client.fetchall(sql, params)
        return [self._row_to_signal(row) for row in rows]

    @staticmethod
    def _row_to_signal(row: dict[str, Any]) -> SignalRecord:
        return SignalRecord(**row)


class IntentWriter:
    """Write trade intent records to the ``trade_intents`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: SignalRecord) -> None:
        """Persist a trade intent record."""
        self._client.execute(
            _INSERT_INTENT,
            (
                record.intent_id,
                record.strategy_id,
                record.signal_date,
                record.instrument_id,
                record.direction,
                record.target_weight,
                record.current_weight,
                record.delta_weight,
                record.quantity,
                record.status,
                record.created_at,
            ),
        )
        self._client.commit()

    def update_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        """Update an intent status with optimistic concurrency protection."""
        placeholders = ", ".join("?" for _ in expected_current)
        sql = _UPDATE_INTENT_STATUS_TRANSITION.format(placeholders=placeholders)
        params = [status, intent_id, *expected_current]
        cursor = self._client.execute(sql, params)
        self._client.commit()
        return cursor.rowcount > 0
