"""
PreTradeRiskCheck — 订单提交前逐单校验 (V3).

V3 完整版包含六条规则：
  - NoShortSellCheck: 卖空校验
  - PriceValidityCheck: 价格有效性校验（涨跌停）
  - LotSizeCheck: 手数校验
  - BuyingPowerCheck: 购买力校验
  - ConcentrationPreCheck: 集中度校验
  - DailyTurnoverPreCheck: 日换手率校验

CompositePreTradeCheck 组合多条规则，支持 resize 后重检（A1）。

Design Doc: v3 §7.2
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from ditto_kernel.identity import (
    InstrumentId as _InstrumentId,
)
from ditto_kernel.order import OrderSide
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
    FeeModel,
    FeeSchedule,
    InstrumentRules,
    MarketSnapshot,
)
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import (
    Order,
    OrderTicket,
    OrderType,
)

from ditto_risk._validation import validate_weight

# Re-export: runtime usage prevents linter removal
# under `from __future__ import annotations`
InstrumentId = _InstrumentId

__all__ = [
    "BuyingPowerCheck",
    "CompositePreTradeCheck",
    "ConcentrationPreCheck",
    "DailyTurnoverPreCheck",
    "Decision",
    "LotSizeCheck",
    "NoShortSellCheck",
    "OrderCheckResult",
    "PreTradeContext",
    "PreTradeRiskCheck",
    "PriceValidityCheck",
]


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


class Decision(StrEnum):
    """PreTrade 校验决策类型。"""

    ACCEPT = "accept"
    REJECT = "reject"
    RESIZE = "resize"


# ---------------------------------------------------------------------------
# PreTradeContext — F1 rolling context (V3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreTradeContext:
    """
    PreTrade 校验所需的只读上下文 — 每笔订单通过后滚动更新。

    V3 完整版：使用 rules + market_snapshots + buying_power_model
    替代 V1 的 estimated_prices / lot_size / fee_schedule。

    Attributes:
        account_view: 账户只读快照
        rules: 三层规则映射 (instrument_id -> InstrumentRules)
        market_snapshots: 市场快照映射 (instrument_id -> MarketSnapshot)
        fee_model: 手续费估算模型
        buying_power_model: 购买力模型
        pending_tickets: 当日已提交待处理订单

    """

    account_view: AccountView
    rules: dict[InstrumentId, InstrumentRules]
    market_snapshots: dict[InstrumentId, MarketSnapshot]
    buying_power_model: BuyingPowerModel
    fee_model: FeeModel | None = None
    pending_tickets: tuple[OrderTicket, ...] = ()

    # -- 辅助方法 ---------------------------------------------------------

    def price_for(self, iid: InstrumentId) -> float | None:
        """从 market_snapshots 获取 close price。"""
        snapshot = self.market_snapshots.get(iid)
        if snapshot is None:
            return None
        return snapshot.close

    def lot_size_for(self, iid: InstrumentId) -> int:
        """从 rules[iid][0].lot_size 获取，默认 DEFAULT_LOT_SIZE。"""
        instrument_rules = self.rules.get(iid)
        if instrument_rules is None:
            return DEFAULT_LOT_SIZE
        return instrument_rules[0].lot_size

    def fee_schedule_for(self, iid: InstrumentId) -> FeeSchedule:
        """从 rules[iid][2] 获取。"""
        instrument_rules = self.rules.get(iid)
        if instrument_rules is None:
            return FeeSchedule(
                instrument_id=InstrumentId(0),
                as_of_date="",
                commission_rate=DEFAULT_COMMISSION_RATE,
                min_commission=DEFAULT_MIN_COMMISSION,
                stamp_duty_rate=0.0,
                transfer_fee_rate=0.0,
            )
        return instrument_rules[2]

    def estimate_order_cost(self, order: Order) -> float:
        """估算订单成本 = price * quantity + fee。"""
        price = self.price_for(order.instrument_id)
        if price is None:
            return 0.0
        cost = order.quantity * price
        fee_schedule = self.fee_schedule_for(order.instrument_id)
        cost += (
            self.fee_model.estimate(order, price, fee_schedule)
            if self.fee_model is not None
            else 0.0
        )
        return cost

    def with_order_accepted(self, order: Order) -> PreTradeContext:
        """返回包含此订单影响的新上下文 — 保持 frozen 语义 (F1)。"""
        price = self.price_for(order.instrument_id)
        if price is None:
            return self

        estimated_cost = self.estimate_order_cost(order)

        if order.direction == OrderSide.BUY:
            new_cash = CashBook(
                available=self.account_view.cash.available - estimated_cost,
                settled=self.account_view.cash.settled,
                frozen=self.account_view.cash.frozen + estimated_cost,
            )
            new_view = replace(
                self.account_view,
                cash=new_cash,
                pending_buy_value=(
                    self.account_view.pending_buy_value + estimated_cost
                ),
            )
        else:
            # B3: 卖出时递减 available_quantity — 防止批内超卖
            position = self.account_view.positions.get(order.instrument_id)
            if position is not None:
                new_available = max(
                    0,
                    position.available_quantity - order.quantity,
                )
                new_position = replace(
                    position,
                    available_quantity=new_available,
                )
                new_positions = dict(self.account_view.positions)
                new_positions[order.instrument_id] = new_position
                new_view = replace(
                    self.account_view,
                    positions=new_positions,
                )
            else:
                new_view = self.account_view

        return replace(
            self,
            account_view=new_view,
        )


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderCheckResult:
    """
    PreTrade 校验结果。

    Attributes:
        decision: 校验决策 (ACCEPT / REJECT / RESIZE)
        order_id: 关联订单 ID
        resized_quantity: RESIZE 时的建议数量 (None = 未 resize)
        reason: 拒绝原因 (None = 通过或无原因)
        triggered_checks: 触发的规则名称列表

    """

    decision: Decision
    order_id: str
    resized_quantity: int | None = None
    reason: str | None = None
    triggered_checks: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class PreTradeRiskCheck(Protocol):
    """订单提交前逐单校验。"""

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """校验单个订单。"""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _accept(order_id: str) -> OrderCheckResult:
    """构建 accept 结果的简写。"""
    return OrderCheckResult(decision=Decision.ACCEPT, order_id=order_id)


# ---------------------------------------------------------------------------
# NoShortSellCheck
# ---------------------------------------------------------------------------


class NoShortSellCheck:
    """卖空校验 — 卖出时持仓 available_quantity 必须 >= order.quantity。"""

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """卖出时检查持仓数量是否充足。"""
        if order.direction == OrderSide.BUY:
            return _accept(order.order_id)

        position = context.account_view.positions.get(order.instrument_id)
        if position is None or position.available_quantity < order.quantity:
            return OrderCheckResult(
                decision=Decision.REJECT,
                order_id=order.order_id,
                reason=(
                    f"no_short_sell: {order.instrument_id} "
                    f"available={position.available_quantity if position else 0}, "
                    f"requested={order.quantity}"
                ),
                triggered_checks=("no_short_sell",),
            )

        return _accept(order.order_id)


# ---------------------------------------------------------------------------
# PriceValidityCheck
# ---------------------------------------------------------------------------


class PriceValidityCheck:
    """价格有效性校验 — LIMIT 单价格在 [limit_down, limit_up] 范围内。"""

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """检查 LIMIT 单价格是否在涨跌停范围内。"""
        if order.order_type != OrderType.LIMIT or order.price is None:
            return _accept(order.order_id)

        snapshot = context.market_snapshots.get(order.instrument_id)
        if snapshot is None:
            return _accept(order.order_id)

        limit_up = snapshot.limit_up
        limit_down = snapshot.limit_down
        if limit_up is None or limit_down is None:
            return _accept(order.order_id)

        if limit_down <= order.price <= limit_up:
            return _accept(order.order_id)

        return OrderCheckResult(
            decision=Decision.REJECT,
            order_id=order.order_id,
            reason=(
                f"price_validity: {order.instrument_id} "
                f"price={order.price} outside "
                f"[{limit_down}, {limit_up}]"
            ),
            triggered_checks=("price_validity",),
        )


# ---------------------------------------------------------------------------
# LotSizeCheck
# ---------------------------------------------------------------------------


class LotSizeCheck:
    """手数校验 — BUY quantity 必须是 lot_size 整数倍。"""

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """检查数量是否满足手数要求，不满足则 resize。"""
        if order.direction == OrderSide.SELL:
            return _accept(order.order_id)

        lot_size = context.lot_size_for(order.instrument_id)
        if lot_size <= 0:
            return _accept(order.order_id)

        if order.quantity > 0 and order.quantity % lot_size == 0:
            return _accept(order.order_id)

        # Resize to next lot_size multiple
        resized = ((order.quantity // lot_size) + 1) * lot_size
        if resized <= 0:
            resized = lot_size

        return OrderCheckResult(
            decision=Decision.RESIZE,
            order_id=order.order_id,
            resized_quantity=resized,
            reason=(
                f"lot_size: {order.quantity} not a multiple of {lot_size}, "
                f"resize to {resized}"
            ),
            triggered_checks=("lot_size",),
        )


# ---------------------------------------------------------------------------
# BuyingPowerCheck
# ---------------------------------------------------------------------------


class BuyingPowerCheck:
    """购买力校验 — buying_power >= estimated_cost。"""

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """检查购买力是否充足。"""
        if order.direction == OrderSide.SELL:
            return _accept(order.order_id)

        cost = context.estimate_order_cost(order)
        available = context.buying_power_model.available_buying_power(
            context.account_view,
            order.direction,
        )

        if available >= cost:
            return _accept(order.order_id)

        return OrderCheckResult(
            decision=Decision.REJECT,
            order_id=order.order_id,
            reason=(
                f"buying_power insufficient: need {cost:.2f}, have {available:.2f}"
            ),
            triggered_checks=("buying_power",),
        )


# ---------------------------------------------------------------------------
# ConcentrationPreCheck
# ---------------------------------------------------------------------------


class ConcentrationPreCheck:
    """集中度校验 — 单标的持仓占比 <= max_weight（默认 20%）。"""

    def __init__(self, max_weight: float = 0.20) -> None:
        validate_weight(max_weight, "max_weight")
        self._max_weight = max_weight

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """检查单标的持仓占比是否超限。"""
        if order.direction == OrderSide.SELL:
            return _accept(order.order_id)

        nav = context.account_view.nav
        if nav <= 0:
            return _accept(order.order_id)

        price = context.price_for(order.instrument_id)
        if price is None:
            return _accept(order.order_id)

        position = context.account_view.positions.get(order.instrument_id)
        current_value = position.market_value if position else 0.0
        total_weight = (current_value + order.quantity * price) / nav

        if total_weight > self._max_weight:
            return OrderCheckResult(
                decision=Decision.REJECT,
                order_id=order.order_id,
                reason=(
                    f"concentration: {order.instrument_id} "
                    f"weight={total_weight:.2%} > max={self._max_weight:.2%}"
                ),
                triggered_checks=("concentration",),
            )

        return _accept(order.order_id)


# ---------------------------------------------------------------------------
# DailyTurnoverPreCheck
# ---------------------------------------------------------------------------


class DailyTurnoverPreCheck:
    """日换手率校验 — 单日累计买入金额 / NAV <= max_turnover（默认 30%）。"""

    def __init__(self, max_turnover: float = 0.30) -> None:
        validate_weight(max_turnover, "max_turnover")
        self._max_turnover = max_turnover

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """检查日累计换手率是否超限。"""
        if order.direction == OrderSide.SELL:
            return _accept(order.order_id)

        nav = context.account_view.nav
        if nav <= 0:
            return _accept(order.order_id)

        # 累计已提交买入金额
        pending_amount = 0.0
        for ticket in context.pending_tickets:
            if ticket.order.direction == OrderSide.BUY:
                ticket_price = context.price_for(ticket.order.instrument_id)
                if ticket_price is not None:
                    pending_amount += ticket.leaves_quantity * ticket_price

        price = context.price_for(order.instrument_id)
        if price is None:
            return _accept(order.order_id)

        turnover = (pending_amount + order.quantity * price) / nav

        if turnover > self._max_turnover:
            return OrderCheckResult(
                decision=Decision.REJECT,
                order_id=order.order_id,
                reason=(
                    f"daily_turnover: turnover={turnover:.2%} "
                    f"> max={self._max_turnover:.2%}"
                ),
                triggered_checks=("daily_turnover",),
            )

        return _accept(order.order_id)


# ---------------------------------------------------------------------------
# CompositePreTradeCheck — A1: resize recheck
# ---------------------------------------------------------------------------

# 默认规则顺序：reject 短路优先，cheap check 在前
DEFAULT_CHECK_ORDER: tuple[type, ...] = (
    NoShortSellCheck,
    PriceValidityCheck,
    LotSizeCheck,
    BuyingPowerCheck,
    ConcentrationPreCheck,
    DailyTurnoverPreCheck,
)


class CompositePreTradeCheck:
    """组合多个 PreTrade 规则，resize 后用新数量重新检查。"""

    MAX_RESIZE_ITERATIONS: int = 3

    def __init__(self, checks: tuple[PreTradeRiskCheck, ...]) -> None:
        self._checks = checks

    def check_order(
        self,
        order: Order,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """组合检查，resize 后重新进入检查链 (A1)。"""
        current_order = order
        triggered: list[str] = []

        for _ in range(self.MAX_RESIZE_ITERATIONS + 1):
            for check in self._checks:
                result = check.check_order(current_order, context)
                if result.decision == Decision.REJECT:
                    return result
                if result.decision == Decision.RESIZE and result.resized_quantity:
                    triggered.extend(result.triggered_checks)
                    current_order = current_order.with_quantity(
                        result.resized_quantity,
                    )
                    break  # Restart check chain with resized order
            else:
                # All checks passed
                resized_qty: int | None = (
                    current_order.quantity
                    if current_order.quantity != order.quantity
                    else None
                )
                return OrderCheckResult(
                    decision=Decision.ACCEPT,
                    order_id=current_order.order_id,
                    resized_quantity=resized_qty,
                    triggered_checks=tuple(triggered),
                )

        return OrderCheckResult(
            decision=Decision.REJECT,
            order_id=order.order_id,
            reason="resize loop detected",
        )
