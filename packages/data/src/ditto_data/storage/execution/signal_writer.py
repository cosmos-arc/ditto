"""SignalWriter — trade_intents 表的 DDL 与写入."""

from __future__ import annotations

from ditto_data.models.trade import SignalRecord
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = [
    "INTENTS_DDL",
    "SignalWriter",
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

_UPDATE_INTENT_STATUS_TRANSITION = (
    "UPDATE trade_intents SET status = ? "
    "WHERE intent_id = ? AND status IN ({placeholders})"
)

INTENTS_DDL = (
    _CREATE_INTENTS_TABLE
    + _CREATE_IDX_INTENTS_STRATEGY_DATE
    + _CREATE_IDX_INTENTS_STATUS
)


class SignalWriter:
    """trade_intents 表的写入与状态更新."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: SignalRecord) -> None:
        """保存交易信号记录."""
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
        """
        更新交易信号状态（乐观并发控制）.

        Args:
            intent_id: 交易意图 ID.
            status: 目标状态.
            expected_current: 期望的当前状态集合，SQL 仅当数据库中的实际状态
                落在该集合内时才执行更新，防止 TOCTOU lost-update。

        Returns:
            True 表示更新成功，False 表示因状态前置条件不满足而跳过。

        """
        placeholders = ", ".join("?" for _ in expected_current)
        sql = _UPDATE_INTENT_STATUS_TRANSITION.format(placeholders=placeholders)
        params = [status, intent_id, *expected_current]
        cursor = self._client.execute(sql, params)
        self._client.commit()
        return cursor.rowcount > 0
