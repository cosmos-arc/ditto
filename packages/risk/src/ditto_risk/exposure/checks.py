"""Exposure pre-trade checks — 集中度等暴露度相关的盘前校验."""

from __future__ import annotations

from ditto_kernel.order import OrderSide

from ditto_risk._validation import validate_weight
from ditto_risk.constraints.context import (
    Decision,
    OrderCheckResult,
    PreTradeContext,
    accept_order,
)
from ditto_risk.contracts import PreTradeOrder

__all__ = ["ConcentrationPreCheck"]


class ConcentrationPreCheck:
    """集中度校验 — 单标的持仓占比 <= max_weight（默认 20%）。"""

    def __init__(self, max_weight: float = 0.20) -> None:
        validate_weight(max_weight, "max_weight")
        self._max_weight = max_weight

    def check_order(
        self,
        order: PreTradeOrder,
        context: PreTradeContext,
    ) -> OrderCheckResult:
        """检查单标的持仓占比是否超限。"""
        if order.direction == OrderSide.SELL:
            return accept_order(order.order_id)

        nav = context.account_view.nav
        if nav <= 0:
            return accept_order(order.order_id)

        price = context.price_for(order.instrument_id)
        if price is None:
            return accept_order(order.order_id)

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

        return accept_order(order.order_id)
