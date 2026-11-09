"""Dated submission constraints shared by backtest and Paper execution."""

from ditto_kernel.order import OrderType
from ditto_kernel.trading import TradingRuleSet

from ditto_execution.orders.model import Order


def order_rule_rejection(order: Order, rule: TradingRuleSet) -> str | None:
    """Return a stable audit reason before any quantity resize or partial fill."""
    if order.order_type.value not in rule.order_types_supported:
        return "unsupported_order_type"
    # MARKET_ON_CLOSE represents the closing auction, not after-hours trading.
    maximum = (
        rule.max_market_order_quantity
        if order.order_type is OrderType.MARKET
        else rule.max_limit_order_quantity
    )
    if maximum is not None:
        if maximum <= 0:
            raise ValueError("maximum order quantity must be positive")
        if order.quantity > maximum:
            return "order_quantity_exceeds_dated_maximum"
    return None
