"""
SlippageModel — 滑点模型协议 + 固定基点实现 + 成交额占比实现.

Phase 3 升级 (R6 三层分离签名):
  estimate(order, market, definition) -> float
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_kernel.order import OrderSide as _OrderSide
from ditto_kernel.trading import InstrumentDefinition as _InstrumentDefinition
from ditto_kernel.trading import MarketSnapshot as _MarketSnapshot
from ditto_portfolio.accounting.order_book import Order as _Order

__all__ = ["FixedBpsSlippage", "SlippageModel", "VolumeShareSlippage"]


class SlippageModel(Protocol):
    """滑点模型协议。"""

    def estimate(
        self,
        order: _Order,
        market: _MarketSnapshot,
        definition: _InstrumentDefinition,
    ) -> float:
        """估算滑点金额（含符号）。BUY 为正，SELL 为负。"""
        ...


@dataclass(frozen=True)
class FixedBpsSlippage:
    """
    固定基点滑点.

    slippage = price * bps / 10_000

    BUY:  price + slippage (买方付更多)
    SELL: price - slippage (卖方收更少)
    """

    bps: float = 2.0

    def estimate(
        self,
        order: _Order,
        market: _MarketSnapshot,
        definition: _InstrumentDefinition,
    ) -> float:
        """估算滑点金额（含符号）。"""
        amount = market.close * self.bps / 10_000
        if order.direction == _OrderSide.BUY:
            return amount
        return -amount


# ---------------------------------------------------------------------------
# VolumeShareSlippage — 成交额占比线性递增
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VolumeShareSlippage:
    """
    按成交额占比线性递增的滑点模型.

    slippage_bps = base_bps + impact_factor × (trade_amount / avg_daily_amount)
    slippage_amount = price × slippage_bps / 10_000

    BUY:  +slippage_amount (买方付更多)
    SELL: -slippage_amount (卖方收更少)

    如果无法估算日均成交额 (avg_volume_20d 缺失或为零), fallback 到 base_bps。
    """

    base_bps: float = 2.0
    impact_factor: float = 0.5

    def estimate(
        self,
        order: _Order,
        market: _MarketSnapshot,
        definition: _InstrumentDefinition,
    ) -> float:
        """估算滑点金额（含符号）。"""
        trade_amount = abs(market.close * order.quantity)

        avg_daily_amount = 0.0
        if market.avg_volume_20d is not None and market.avg_volume_20d > 0:
            avg_daily_amount = market.avg_volume_20d * market.close

        if avg_daily_amount > 0:
            share = trade_amount / avg_daily_amount
            bps = self.base_bps + self.impact_factor * share
        else:
            bps = self.base_bps

        amount = market.close * bps / 10_000
        if order.direction == _OrderSide.BUY:
            return amount
        return -amount
