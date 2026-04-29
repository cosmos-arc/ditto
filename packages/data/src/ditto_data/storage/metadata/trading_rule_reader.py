"""TradingRuleReader -- PIT 版本化交易规则查询."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import orjson
from ditto_infra.foundation import SQLitePool
from ditto_kernel.identity import InstrumentId as _InstrumentId

from ditto_data.storage.metadata._pit_base import PITRecordReader

InstrumentId = _InstrumentId

__all__ = ["SQLiteTradingRuleReader", "TradingRuleReader", "TradingRuleRecord"]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_PIT_QUERY = """
SELECT instrument_id, as_of_date, settlement_cycle, fund_settlement_cycle,
       price_limit_pct, order_types_supported, call_auction_sessions,
       effective_from, effective_to
FROM trading_rule
WHERE instrument_id = ?
  AND effective_from <= ?
  AND (effective_to IS NULL OR effective_to > ?)
ORDER BY effective_from DESC
LIMIT 1
"""

_SELECT_ALL = """
SELECT instrument_id, as_of_date, settlement_cycle, fund_settlement_cycle,
       price_limit_pct, order_types_supported, call_auction_sessions,
       effective_from, effective_to
FROM trading_rule
"""


@dataclass(frozen=True)
class TradingRuleRecord:
    """
    交易规则持久化记录（含 PIT 字段）.

    Attributes:
        instrument_id: 标的 ID.
        as_of_date: 规则生效日期 (YYYY-MM-DD).
        settlement_cycle: T+N 结算周期.
        fund_settlement_cycle: 资金交收 T+N.
        price_limit_pct: 涨跌停限制 (None = 无限制).
        order_types_supported: 支持的订单类型.
        call_auction_sessions: 集合竞价时段.
        effective_from: 版本生效日期（含）.
        effective_to: 版本失效日期（不含）, NULL 表示当前版本.

    """

    instrument_id: InstrumentId
    as_of_date: str
    settlement_cycle: int
    fund_settlement_cycle: int
    price_limit_pct: float | None
    order_types_supported: tuple[str, ...]
    call_auction_sessions: tuple[str, ...]
    effective_from: str
    effective_to: str | None = None


class TradingRuleReader(PITRecordReader[TradingRuleRecord]):
    """交易规则 Reader -- PIT 版本化查询. V1 内存实现."""


class SQLiteTradingRuleReader(PITRecordReader[TradingRuleRecord]):
    """交易规则 Reader -- SQLite PIT 版本化查询."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    def get(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> TradingRuleRecord | None:
        """
        PIT 查询: 获取指定标的在 as_of_date 时有效的记录.

        查询条件:
            effective_from <= as_of_date
            AND (effective_to IS NULL OR effective_to > as_of_date)

        多个版本匹配时，返回 effective_from 最大的版本.
        """
        conn = self._pool.get_connection()
        row = conn.execute(
            _PIT_QUERY, (instrument_id, as_of_date, as_of_date)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_all(self) -> list[TradingRuleRecord]:
        """获取所有交易规则记录."""
        conn = self._pool.get_connection()
        rows = conn.execute(_SELECT_ALL).fetchall()
        return [self._row_to_record(row) for row in rows]

    def _row_to_record(self, row: sqlite3.Row) -> TradingRuleRecord:
        """将数据库行转换为 TradingRuleRecord."""
        return TradingRuleRecord(
            instrument_id=InstrumentId(row["instrument_id"]),
            as_of_date=row["as_of_date"],
            settlement_cycle=row["settlement_cycle"],
            fund_settlement_cycle=row["fund_settlement_cycle"],
            price_limit_pct=row["price_limit_pct"],
            order_types_supported=tuple(orjson.loads(row["order_types_supported"])),
            call_auction_sessions=tuple(orjson.loads(row["call_auction_sessions"])),
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
        )
