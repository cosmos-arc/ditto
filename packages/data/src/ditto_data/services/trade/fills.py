"""FillWriter — execution_fills 表的 DDL 与 CRUD."""

from __future__ import annotations

from typing import Any

from ditto_data.models.trade import ManualExecutionFillRecord
from ditto_data.storage.sqlite_client import SQLiteClient

# ---------------------------------------------------------------------------
# SQL: execution_fills
# ---------------------------------------------------------------------------

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
INSERT INTO execution_fills
    (fill_id, intent_id, strategy_id, trade_date, instrument_id, direction,
     quantity, fill_price, fee, slippage, notes, settlement_date, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_FILL_BY_ID = "SELECT * FROM execution_fills WHERE fill_id = ?"

_FIND_FILL_BY_INTENT_AND_DATE = (
    "SELECT * FROM execution_fills WHERE intent_id = ? AND trade_date = ? LIMIT 1"
)

_LIST_FILLS_BASE = "SELECT * FROM execution_fills WHERE strategy_id = ?"

# ---------------------------------------------------------------------------
# DDL (public, 供 service.py 调用)
# ---------------------------------------------------------------------------

FILLS_DDL = (
    _CREATE_FILLS_TABLE + _CREATE_IDX_FILLS_STRATEGY_DATE + _CREATE_IDX_FILLS_INTENT
)


class FillWriter:
    """execution_fills 表的写入/查询."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: ManualExecutionFillRecord) -> None:
        """保存人工成交记录."""
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

    def get(self, fill_id: str) -> ManualExecutionFillRecord | None:
        """按 fill_id 查询单条成交记录."""
        row = self._client.fetchone(_SELECT_FILL_BY_ID, (fill_id,))
        return self._row_to_fill(row) if row else None

    def find(self, intent_id: str, trade_date: str) -> ManualExecutionFillRecord | None:
        """按 intent_id + trade_date 查找成交记录（幂等去重用）。"""
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
    ) -> list[ManualExecutionFillRecord]:
        """按条件查询成交记录列表."""
        clauses: list[str] = []
        params: list[Any] = [strategy_id]

        if trade_date is not None and end_date is not None:
            clauses.append("trade_date >= ?")
            params.append(trade_date)
            clauses.append("trade_date <= ?")
            params.append(end_date)
        elif trade_date is not None:
            clauses.append("trade_date = ?")
            params.append(trade_date)
        elif end_date is not None:
            clauses.append("trade_date <= ?")
            params.append(end_date)

        if intent_id is not None:
            clauses.append("intent_id = ?")
            params.append(intent_id)

        where = (" AND " + " AND ".join(clauses)) if clauses else ""
        sql = _LIST_FILLS_BASE + where + " ORDER BY trade_date ASC"

        rows = self._client.fetchall(sql, params)
        return [self._row_to_fill(row) for row in rows]

    @staticmethod
    def _row_to_fill(row: dict[str, Any]) -> ManualExecutionFillRecord:
        """将数据库行字典转换为 ManualExecutionFillRecord."""
        return ManualExecutionFillRecord(**row)
