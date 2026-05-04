"""Pre-trade constraint checks — 订单提交前的逐单校验规则实现."""

from __future__ import annotations

from typing import Protocol

from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting.order_book import Order

from ditto_risk._validation import validate_weight
from ditto_risk.constraints.context import (
    Decision,
    OrderCheckResult,
    PreTradeContext,
)

__all__ = [
    "BuyingPowerCheck",
    "CompositePreTradeCheck",
    "DailyTurnoverPreCheck",
    "LotSizeCheck",
    "NoShortSellCheck",
    "PreTradeRiskCheck",
    "PriceValidityCheck",
]


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
