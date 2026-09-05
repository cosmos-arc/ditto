"""Fail-closed valuation tests for pending and batch-local turnover evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting import Account, CashAccountBuyingPower, CashBook
from ditto_risk._turnover import pending_order_notional
from ditto_risk.constraints.context import PreTradeContext

_IID = InstrumentId(1)


@dataclass(frozen=True)
class _Order:
    instrument_id: InstrumentId = _IID
    quantity: int = 10
    direction: OrderSide = OrderSide.BUY
    order_id: str = "order-1"
    order_type: OrderType = OrderType.LIMIT
    price: float | None = 10.0

    def with_quantity(self, qty: int) -> _Order:
        return replace(self, quantity=qty)


@dataclass(frozen=True)
class _Ticket:
    order: _Order
    leaves_quantity: int


def _quote(close: float = 11.0) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-09-04",
        instrument_id=_IID,
        open=close,
        high=close,
        low=close,
        close=close,
        prev_close=close,
        volume=1.0,
        amount=close,
    )


def _context(
    *,
    pending: tuple[_Ticket, ...] = (),
    accepted: tuple[_Order, ...] = (),
    quote: MarketSnapshot | None = None,
) -> PreTradeContext:
    return PreTradeContext(
        account_view=Account(
            cash=CashBook(available=1_000.0, settled=1_000.0, frozen=0.0)
        ).get_view(),
        rules={},
        market_snapshots={} if quote is None else {_IID: quote},
        buying_power_model=CashAccountBuyingPower(),
        pending_tickets=pending,
        accepted_orders=accepted,
    )


def test_absent_or_empty_pending_evidence_has_zero_notional() -> None:
    assert pending_order_notional(None) == 0.0
    assert pending_order_notional(_context()) == 0.0


def test_pending_ticket_uses_leaves_quantity_and_market_fallback() -> None:
    context = _context(
        pending=(
            _Ticket(_Order(price=10.0), leaves_quantity=0),
            _Ticket(_Order(price=None), leaves_quantity=3),
        ),
        quote=_quote(11.0),
    )

    assert pending_order_notional(context) == 33.0


@pytest.mark.parametrize("quantity", [True, -1])
def test_pending_ticket_rejects_noncanonical_leaves_quantity(quantity: object) -> None:
    ticket = _Ticket(_Order(), leaves_quantity=cast(int, quantity))
    assert pending_order_notional(_context(pending=(ticket,))) is None


@pytest.mark.parametrize("price", [None, 0.0, -1.0, float("nan")])
def test_pending_ticket_rejects_missing_or_invalid_price(price: float | None) -> None:
    ticket = _Ticket(_Order(price=price), leaves_quantity=1)
    assert pending_order_notional(_context(pending=(ticket,))) is None


def test_accepted_order_uses_explicit_and_market_fallback_prices() -> None:
    context = _context(
        accepted=(
            _Order(quantity=2, price=10.0),
            _Order(order_id="order-2", quantity=3, price=None),
        ),
        quote=_quote(11.0),
    )

    assert pending_order_notional(context) == 53.0


@pytest.mark.parametrize("quantity", [True, 0, -1])
def test_accepted_order_rejects_non_positive_integer_quantity(quantity: object) -> None:
    order = _Order(quantity=cast(int, quantity))
    assert pending_order_notional(_context(accepted=(order,))) is None


@pytest.mark.parametrize("price", [None, 0.0, -1.0, float("inf")])
def test_accepted_order_rejects_missing_or_invalid_price(price: float | None) -> None:
    assert pending_order_notional(_context(accepted=(_Order(price=price),))) is None
