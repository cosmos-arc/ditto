"""Dated submission constraints shared by backtest and Paper execution."""

from ditto_kernel.order import OrderSide as _OrderSide
from ditto_kernel.order import OrderType as _OrderType
from ditto_kernel.trading import TradingRuleSet as _TradingRuleSet

from ditto_execution.orders.model import Order


def order_rule_rejection(order: Order, rule: _TradingRuleSet) -> str | None:
    """Return a stable audit reason before any quantity resize or partial fill."""
    if order.order_type.value not in rule.order_types_supported:
        return "unsupported_order_type"
    # MARKET_ON_CLOSE represents the closing auction, not after-hours trading.
    maximum = (
        rule.max_market_order_quantity
        if order.order_type is _OrderType.MARKET
        else rule.max_limit_order_quantity
    )
    if maximum is not None:
        if maximum <= 0:
            raise ValueError("maximum order quantity must be positive")
        if order.quantity > maximum:
            return "order_quantity_exceeds_dated_maximum"
    return None


def minimum_order_rejection(
    order: Order, rule: _TradingRuleSet, *, position_quantity: int
) -> str | None:
    """Validate a new submission, never a partly filled order's remaining shares."""
    if rule.min_order_quantity <= 0:
        raise ValueError("minimum order quantity must be positive")
    if order.quantity >= rule.min_order_quantity:
        return None
    if order.direction is _OrderSide.BUY:
        return "order_quantity_below_dated_minimum"
    if order.quantity != position_quantity:
        return "sell_below_minimum_requires_full_liquidation"
    return None


def daily_buy_rejection(
    order: Order, rule: _TradingRuleSet, *, bought_quantity: int, pending_quantity: int
) -> str | None:
    """Dated daily ST cap includes executed and still-open buys, never sells."""
    cap = rule.max_daily_buy_quantity
    if cap is None or order.direction is _OrderSide.SELL:
        return None
    if cap <= 0 or min(bought_quantity, pending_quantity) < 0:
        raise ValueError("invalid daily buy limit inputs")
    if order.quantity + bought_quantity + pending_quantity > cap:
        return "daily_buy_quantity_exceeds_dated_maximum"
    return None
