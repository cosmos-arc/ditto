"""SignalReader — trade_intents 表的查询."""

from __future__ import annotations

from typing import Any

from ditto_execution.models import SignalRecord
from ditto_execution.storage.sqlite.legacy._sql import build_where_clause
from ditto_execution.storage.sqlite_client import SQLiteClient

__all__ = [
    "SignalReader",
]

_SELECT_INTENT_BY_ID = "SELECT * FROM trade_intents WHERE intent_id = ?"

_LIST_INTENTS_BASE = "SELECT * FROM trade_intents WHERE strategy_id = ?"


class SignalReader:
    """trade_intents 表的只读查询."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get(self, intent_id: str) -> SignalRecord | None:
        """按 intent_id 查询单条交易信号."""
        row = self._client.fetchone(_SELECT_INTENT_BY_ID, (intent_id,))
        return self._row_to_signal(row) if row else None

    def list(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        """按条件查询交易信号列表."""
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
