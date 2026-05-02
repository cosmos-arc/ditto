"""FillReader — execution_fills 表的查询."""

from __future__ import annotations

from typing import Any

from ditto_execution.models import FillRecord
from ditto_execution.storage.sqlite.legacy._sql import build_where_clause
from ditto_execution.storage.sqlite_client import SQLiteClient

__all__ = [
    "FillReader",
]

_SELECT_FILL_BY_ID = "SELECT * FROM execution_fills WHERE fill_id = ?"

_FIND_FILL_BY_INTENT_AND_DATE = (
    "SELECT * FROM execution_fills WHERE intent_id = ? AND trade_date = ? LIMIT 1"
)

_LIST_FILLS_BASE = "SELECT * FROM execution_fills WHERE strategy_id = ?"


class FillReader:
    """execution_fills 表的只读查询."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get(self, fill_id: str) -> FillRecord | None:
        """按 fill_id 查询单条成交记录."""
        row = self._client.fetchone(_SELECT_FILL_BY_ID, (fill_id,))
        return self._row_to_fill(row) if row else None

    def find(self, intent_id: str, trade_date: str) -> FillRecord | None:
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
    ) -> list[FillRecord]:
        """
        按条件查询成交记录列表.

        日期过滤逻辑（通过 build_where_clause 构建）：
          - 仅 trade_date → 精确匹配
          - 仅 end_date → trade_date <= end_date（半开区间）
          - 两者均提供 → trade_date >= trade_date AND trade_date <= end_date（闭区间）
        """
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
