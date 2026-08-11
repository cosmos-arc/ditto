"""Pure turnover valuation helpers for continuous pre-trade risk."""

from __future__ import annotations

import math

from ditto_risk.constraints.context import PreTradeContext

__all__ = ["pending_order_notional"]


def pending_order_notional(context: PreTradeContext | None) -> float | None:
    """Value authoritative pending tickets and accepted batch-local orders."""
    if context is None:
        return 0.0
    pending_total = _pending_ticket_notional(context)
    accepted_total = _accepted_order_notional(context)
    if pending_total is None or accepted_total is None:
        return None
    total = pending_total + accepted_total
    return total if math.isfinite(total) else None


def _pending_ticket_notional(context: PreTradeContext) -> float | None:
    total = 0.0
    for ticket in context.pending_tickets:
        quantity = ticket.leaves_quantity
        if type(quantity) is not int or quantity < 0:
            return None
        if quantity == 0:
            continue
        price = ticket.order.price
        if price is None:
            price = context.price_for(ticket.order.instrument_id)
        if price is None or not math.isfinite(price) or price <= 0.0:
            return None
        total += price * quantity
    return total


def _accepted_order_notional(context: PreTradeContext) -> float | None:
    total = 0.0
    for order in context.accepted_orders:
        quantity = order.quantity
        if type(quantity) is not int or quantity <= 0:
            return None
        price = order.price
        if price is None:
            price = context.price_for(order.instrument_id)
        if price is None or not math.isfinite(price) or price <= 0.0:
            return None
        total += price * quantity
    return total
