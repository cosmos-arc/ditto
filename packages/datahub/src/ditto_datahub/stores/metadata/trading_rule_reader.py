"""TradingRuleReader -- PIT 版本化交易规则查询."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_datahub.stores.metadata._pit_base import PITRecordReader

__all__ = ["TradingRuleReader", "TradingRuleRecord"]


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

    instrument_id: str
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
