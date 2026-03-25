"""
FillModel — 成交模型协议 + 简单实现 + A 股实现.

Phase 3 升级 (R6 三层分离签名):
  try_fill(order, market, definition, trading_rule) -> FillOutcome
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_kernel.enums import OrderSide as OrderDirection

from ditto_core.accounting.order_book import Order, OrderType
from ditto_core.execution.fills import Filled, FillEvent, FillOutcome, NoFill
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_core.execution.rules import InstrumentDefinition, TradingRuleSet

__all__ = [
    "AShareFillModel",
    "ClosingAuctionFillModel",
    "FillModel",
    "SimpleFillModel",
]


class FillModel(Protocol):
    """成交模型协议 -- 接收订单和市场数据，返回成交结果。"""

    def try_fill(
        self,
        order: Order,
        market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillOutcome:
        """尝试成交。"""
        ...


# ---------------------------------------------------------------------------
# SimpleFillModel — fallback + 测试用
# ---------------------------------------------------------------------------


class SimpleFillModel:
    """
    简单成交模型 — fallback + 测试用.

    - MARKET 单: 以 close 成交 (不含滑点, 由 Brokerage 添加)
    - LIMIT 单: 限价在 [low, high] 内以限价成交;
      限价超出范围则 NoFill(can_retry=False)
    - 其他类型: NoFill(can_retry=False)

    注意: 滑点由 BacktestBrokerage 在构建 FillEvent 时添加,
    FillModel 仅决定是否成交及基准成交价。
    """

    def try_fill(
        self,
        order: Order,
        market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillOutcome:
        """尝试成交。"""
        if order.order_type == OrderType.MARKET:
            fill_price = market.close
            return _make_filled(order, fill_price)

        if order.order_type == OrderType.LIMIT:
            limit_price = order.price
            if limit_price is None or not (market.low <= limit_price <= market.high):
                return NoFill(reason="price_out_of_range", can_retry=False)
            return _make_filled(order, limit_price)

        return NoFill(reason="unsupported_order_type", can_retry=False)


# ---------------------------------------------------------------------------
# ClosingAuctionFillModel — 收盘集合竞价
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosingAuctionFillModel:
    """
    收盘集合竞价成交模型.

    成交比例 = min(1.0, participation_rate_threshold × avg_volume_20d / order.quantity)
    如果 avg_volume_20d 缺失或为零, 以 close 全量成交 (fallback)。
    """

    participation_rate_threshold: float = 0.05

    def try_fill(
        self,
        order: Order,
        market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillOutcome:
        """尝试收盘集合竞价成交。"""
        avg_vol = market.avg_volume_20d

        if avg_vol is None or avg_vol <= 0:
            # Fallback: 无日均量数据, 全量成交
            return _make_filled(order, market.close)

        max_acceptable = avg_vol * self.participation_rate_threshold
        if order.quantity <= max_acceptable:
            return _make_filled(order, market.close)

        # 部分成交
        filled_qty = max(0, int(order.quantity * max_acceptable / order.quantity))
        if filled_qty == 0:
            return NoFill(reason="insufficient_auction", can_retry=False)

        return _make_filled(order, market.close, filled_qty=filled_qty)


# ---------------------------------------------------------------------------
# AShareFillModel — A 股完整成交模型
# ---------------------------------------------------------------------------


class AShareFillModel:
    """
    A 股成交模型 — 涨跌停/停牌/集合竞价规则矩阵.

    规则矩阵:
    | 场景                    | 结果                              |
    |------------------------|----------------------------------|
    | 停牌                    | NoFill(can_retry=True)            |
    | 涨停 + 买入             | NoFill(can_retry=True)            |
    | 跌停 + 卖出             | NoFill(can_retry=True)            |
    | 涨停 + 卖出             | Filled at close                   |
    | 跌停 + 买入             | Filled at close                   |
    | MARKET_ON_CLOSE         | 委托 ClosingAuctionFillModel      |
    | LIMIT 单: 在 [low,high] | Filled at limit_price             |
    | LIMIT 单: 超出范围      | NoFill(can_retry=False)           |
    | MARKET 单 (正常)        | Filled at close                   |
    """

    def __init__(
        self,
        auction_model: ClosingAuctionFillModel | None = None,
    ) -> None:
        self._auction = auction_model or ClosingAuctionFillModel()

    def try_fill(
        self,
        order: Order,
        market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillOutcome:
        """A 股规则矩阵成交。"""
        outcome = self._evaluate(order, market, definition, trading_rule)
        if outcome is not None:
            return outcome
        return NoFill(reason="unsupported_order_type", can_retry=False)

    def _evaluate(
        self,
        order: Order,
        market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillOutcome | None:
        """A 股规则矩阵 — 返回 None 表示未匹配任何规则。"""
        # 停牌
        if market.is_suspended:
            return NoFill(reason="suspended", can_retry=True)

        # MARKET_ON_CLOSE 委托竞价模型
        if order.order_type == OrderType.MARKET_ON_CLOSE:
            return self._auction.try_fill(order, market, definition, trading_rule)

        # 涨跌停判断
        at_limit_up = market.limit_up is not None and market.close >= market.limit_up
        at_limit_down = (
            market.limit_down is not None and market.close <= market.limit_down
        )

        # 涨停 + 买入 或 跌停 + 卖出 → 无法成交
        if (at_limit_up and order.direction == OrderDirection.BUY) or (
            at_limit_down and order.direction == OrderDirection.SELL
        ):
            reason = "limit_up_no_buy" if at_limit_up else "limit_down_no_sell"
            return NoFill(reason=reason, can_retry=True)

        # MARKET / LIMIT 单 — 使用 _fill_by_type 统一分发
        if order.order_type in (OrderType.MARKET, OrderType.LIMIT):
            return self._fill_by_type(order, market)

        return None

    def _fill_by_type(self, order: Order, market: MarketSnapshot) -> FillOutcome:
        """MARKET / LIMIT 成交逻辑。"""
        if order.order_type == OrderType.MARKET:
            return _make_filled(order, market.close)

        # LIMIT 单
        limit_price = order.price
        if limit_price is None or not (market.low <= limit_price <= market.high):
            return NoFill(reason="price_out_of_range", can_retry=False)
        return _make_filled(order, limit_price)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _make_filled(
    order: Order,
    fill_price: float,
    filled_qty: int | None = None,
) -> Filled:
    """构造 Filled 占位 -- FillEvent 字段由 Brokerage 补全。"""
    qty = filled_qty if filled_qty is not None else order.quantity
    fill_event = FillEvent(
        fill_id="",
        order_id=order.order_id,
        instrument_id=order.instrument_id,
        direction=order.direction,
        filled_quantity=qty,
        fill_price=fill_price,
        fee=0.0,
        slippage=0.0,
        event_time=order.created_at,
        cumulative_quantity=0,
        leaves_quantity=order.quantity - qty,
    )
    return Filled(fill_event=fill_event)
