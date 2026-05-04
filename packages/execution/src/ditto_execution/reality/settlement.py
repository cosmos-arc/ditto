"""
SettlementModel — 交收模型协议 + 简单实现 + A 股实现.

Phase 3 升级 (R6 三层分离签名):
  is_tradable(instrument_id, trade_date, direction, position, trading_rule) -> bool
  settle_date(trade_date, trading_rule) -> str
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ditto_kernel.identity import InstrumentId as _InstrumentId
from ditto_kernel.order import OrderSide as _OrderSide
from ditto_kernel.trading import TradingRuleSet as _TradingRuleSet
from ditto_portfolio.accounting.position import Position as _Position

__all__ = ["AShareSettlementModel", "SettlementModel", "SimpleSettlementModel"]


class SettlementModel(Protocol):
    """交收模型协议。"""

    def is_tradable(
        self,
        instrument_id: _InstrumentId,
        trade_date: str,
        direction: _OrderSide,
        position: _Position | None,
        trading_rule: _TradingRuleSet,
    ) -> bool:
        """检查标的在指定日期是否可交易。"""
        ...

    def settle_date(
        self,
        trade_date: str,
        trading_rule: _TradingRuleSet,
    ) -> str:
        """计算交收日期。"""
        ...


class SimpleSettlementModel:
    """简单交收模型 — 始终可交易, T+0 交收。"""

    def is_tradable(
        self,
        instrument_id: _InstrumentId,
        trade_date: str,
        direction: _OrderSide,
        position: _Position | None,
        trading_rule: _TradingRuleSet,
    ) -> bool:
        """始终返回 True。仅满足 SettlementModel Protocol 接口契约。"""
        return True

    def settle_date(
        self,
        trade_date: str,
        trading_rule: _TradingRuleSet,
    ) -> str:
        """T+0 交收 — 当日即交收。"""
        return trade_date


# ---------------------------------------------------------------------------
# AShareSettlementModel — T+0/T+1 交收
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AShareSettlementModel:
    """
    A 股交收模型 — 根据 settlement_cycle 计算交收日期.

    T+1 买入冻结逻辑在 Brokerage 层实现, SettlementModel 仅提供:
    - is_tradable(): 买入始终 True, 卖出始终 True (冻结由 Brokerage 管理)
    - settle_date(): 计算 T+N 交收日期

    Parameters
    ----------
        trading_calendar: 排序后的交易日历 (YYYY-MM-DD), 空则 fallback 到日历加 N 天

    """

    trading_calendar: tuple[str, ...] = ()

    def is_tradable(
        self,
        instrument_id: _InstrumentId,
        trade_date: str,
        direction: _OrderSide,
        position: _Position | None,
        trading_rule: _TradingRuleSet,
    ) -> bool:
        """
        A 股场景始终返回 True。

        卖出可交易性由 Brokerage 的冻结份额（frozen_quantity）机制控制，
        而非 SettlementModel。本方法仅满足 SettlementModel Protocol 接口契约。

        """
        return True

    def settle_date(
        self,
        trade_date: str,
        trading_rule: _TradingRuleSet,
    ) -> str:
        """计算 T+N 交收日期 — 从交易日历中跳过非交易日。"""
        cycle = trading_rule.settlement_cycle
        if cycle == 0:
            return trade_date

        if not self.trading_calendar:
            dt = datetime.strptime(trade_date, "%Y-%m-%d")
            return (dt + timedelta(days=cycle)).strftime("%Y-%m-%d")

        try:
            idx = self.trading_calendar.index(trade_date)
        except ValueError:
            dt = datetime.strptime(trade_date, "%Y-%m-%d")
            return (dt + timedelta(days=cycle)).strftime("%Y-%m-%d")

        target_idx = idx + cycle
        if target_idx < len(self.trading_calendar):
            return self.trading_calendar[target_idx]

        # 超出日历范围, fallback
        dt = datetime.strptime(trade_date, "%Y-%m-%d")
        return (dt + timedelta(days=cycle)).strftime("%Y-%m-%d")
