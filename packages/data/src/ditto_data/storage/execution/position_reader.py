"""PositionReader — actual_positions 表的查询."""

from __future__ import annotations

from typing import Any

from ditto_data.models.trade import PositionRecord
from ditto_data.storage.execution._sql import build_where_clause
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = [
    "PositionReader",
]

_GET_LATEST_POSITION = """
SELECT * FROM actual_positions
WHERE strategy_id = ? AND instrument_id = ?
ORDER BY snapshot_date DESC
LIMIT 1
"""

_LIST_POSITIONS_BASE = "SELECT * FROM actual_positions WHERE strategy_id = ?"


class PositionReader:
    """actual_positions 表的只读查询."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get_latest(self, strategy_id: str, instrument_id: int) -> PositionRecord | None:
        """查询指定策略/标的的最新持仓快照."""
        row = self._client.fetchone(_GET_LATEST_POSITION, (strategy_id, instrument_id))
        return self._row_to_position(row) if row else None

    def list(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
    ) -> list[PositionRecord]:
        """按条件查询持仓快照列表."""
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
