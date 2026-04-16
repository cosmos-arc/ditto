"""TradeIntentWriter — trade_intents 表的 DDL 与 CRUD."""

from __future__ import annotations

from typing import Any

from ditto_data.models.trade import TradeIntentRecord
from ditto_data.services.trade._sql import build_where_clause
from ditto_data.storage.sqlite_client import SQLiteClient

# ---------------------------------------------------------------------------
# SQL: trade_intents
# ---------------------------------------------------------------------------

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

_UPDATE_INTENT_STATUS = "UPDATE trade_intents SET status = ? WHERE intent_id = ?"

_UPDATE_INTENT_STATUS_TRANSITION = (
    "UPDATE trade_intents SET status = ? "
    "WHERE intent_id = ? AND status IN ({placeholders})"
)

# ---------------------------------------------------------------------------
# DDL (public, 供 service.py 调用)
# ---------------------------------------------------------------------------

INTENTS_DDL = (
    _CREATE_INTENTS_TABLE
    + _CREATE_IDX_INTENTS_STRATEGY_DATE
    + _CREATE_IDX_INTENTS_STATUS
)


class TradeIntentWriter:
    """trade_intents 表的写入/查询/状态更新."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: TradeIntentRecord) -> None:
        """保存交易意图记录."""
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

    def get(self, intent_id: str) -> TradeIntentRecord | None:
        """按 intent_id 查询单条交易意图."""
        row = self._client.fetchone(_SELECT_INTENT_BY_ID, (intent_id,))
        return self._row_to_intent(row) if row else None

    def list(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[TradeIntentRecord]:
        """按条件查询交易意图列表."""
        sql, params = build_where_clause(
            _LIST_INTENTS_BASE,
            strategy_id,
            {"signal_date": signal_date, "status": status},
            "signal_date ASC",
        )
        rows = self._client.fetchall(sql, params)
        return [self._row_to_intent(row) for row in rows]

    def update_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...] | None = None,
    ) -> bool:
        """
        更新交易意图状态.

        Returns:
            True 表示更新成功，False 表示因状态前置条件不满足而跳过。

        """
        if expected_current is None:
            self._client.execute(_UPDATE_INTENT_STATUS, (status, intent_id))
            self._client.commit()
            return True

        placeholders = ", ".join("?" for _ in expected_current)
        sql = _UPDATE_INTENT_STATUS_TRANSITION.format(placeholders=placeholders)
        params: list[Any] = [status, intent_id, *expected_current]
        cursor = self._client.execute(sql, params)
        self._client.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_intent(row: dict[str, Any]) -> TradeIntentRecord:
        """将数据库行字典转换为 TradeIntentRecord."""
        return TradeIntentRecord(**row)
