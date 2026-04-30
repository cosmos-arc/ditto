"""Tests for OrderBook / OrderTicket (F5: frozen)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime

import pytest
from ditto_portfolio.accounting.order_book import (
    Order,
    OrderBook,
    OrderEvent,
    OrderSide,
    OrderStatus,
    OrderTicket,
    OrderType,
    StateTransitionError,
)


def _make_order(
    order_id: str = "ORD-001",
    instrument_id: int = 1,
    quantity: int = 100,
    price: float | None = None,
) -> Order:
    """Helper to create a minimal Order for testing."""
    return Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=quantity,
        price=price,
        created_at=datetime(2026, 1, 15, 10, 30, 0),
        strategy_run_id="RUN-001",
    )


class TestOrder:
    def test_create_market_order(self) -> None:
        order = _make_order()
        assert order.order_id == "ORD-001"
        assert order.instrument_id == 1
        assert order.quantity == 100
        assert order.price is None
        assert order.direction == OrderSide.BUY

    def test_order_is_frozen(self) -> None:
        order = _make_order()
        with pytest.raises(FrozenInstanceError):
            order.quantity = 200  # type: ignore[misc]

    def test_order_with_quantity(self) -> None:
        order = _make_order(quantity=100)
        resized = order.with_quantity(200)
        assert resized.quantity == 200
        assert order.quantity == 100  # 原实例不变

    def test_create_limit_order(self) -> None:
        order = _make_order(price=0.460)
        assert order.order_type == OrderType.MARKET  # default
        # 需要显式创建 limit order
        limit_order = replace(order, order_type=OrderType.LIMIT, price=0.460)
        assert limit_order.price == 0.460


class TestOrderStatus:
    def test_terminal_states(self) -> None:
        terminal = {
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.INVALID,
        }
        for status in OrderStatus:
            if status in terminal:
                assert status.is_terminal
            else:
                assert not status.is_terminal


class TestOrderEvent:
    def test_create_order_event(self) -> None:
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.SUBMITTED,
            timestamp=datetime(2026, 1, 15, 10, 30, 1),
        )
        assert event.order_id == "ORD-001"
        assert event.fill_price is None
        assert event.fee == 0.0

    def test_create_fill_event(self) -> None:
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.PARTIALLY_FILLED,
            fill_price=0.452,
            fill_quantity=100,
            fee=2.26,
            timestamp=datetime(2026, 1, 15, 10, 30, 5),
        )
        assert event.fill_price == 0.452
        assert event.fill_quantity == 100
        assert event.fee == 2.26


class TestOrderTicket:
    def test_create_ticket(self) -> None:
        order = _make_order()
        ticket = OrderTicket(order=order)
        assert ticket.status == OrderStatus.NEW
        assert ticket.filled_quantity == 0
        assert ticket.leaves_quantity == 100

    def test_ticket_is_frozen(self) -> None:
        ticket = OrderTicket(order=_make_order())
        with pytest.raises(FrozenInstanceError):
            ticket.status = OrderStatus.SUBMITTED  # type: ignore[misc]

    def test_with_fill_partial(self) -> None:
        order = _make_order(quantity=200)
        ticket = OrderTicket(order=order)
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.PARTIALLY_FILLED,
            fill_price=0.452,
            fill_quantity=100,
            timestamp=datetime(2026, 1, 15, 10, 30, 5),
        )
        new_ticket = ticket.with_fill(quantity=100, price=0.452, event=event)
        assert new_ticket.filled_quantity == 100
        assert new_ticket.leaves_quantity == 100
        assert new_ticket.status == OrderStatus.PARTIALLY_FILLED
        assert len(new_ticket.order_events) == 1
        # 原实例不变
        assert ticket.filled_quantity == 0

    def test_with_fill_full(self) -> None:
        order = _make_order(quantity=200)
        ticket = OrderTicket(order=order)
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.FILLED,
            fill_price=0.452,
            fill_quantity=200,
            timestamp=datetime(2026, 1, 15, 10, 30, 5),
        )
        new_ticket = ticket.with_fill(quantity=200, price=0.452, event=event)
        assert new_ticket.filled_quantity == 200
        assert new_ticket.leaves_quantity == 0
        assert new_ticket.status == OrderStatus.FILLED

    def test_with_cancel(self) -> None:
        ticket = OrderTicket(order=_make_order())
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 15, 11, 0, 0),
            message="user_cancel",
        )
        new_ticket = ticket.with_cancel(event)
        assert new_ticket.status == OrderStatus.CANCELED
        assert new_ticket.order_events[0].message == "user_cancel"

    def test_with_cancel_terminal_raises(self) -> None:
        ticket = OrderTicket(
            order=_make_order(),
            status=OrderStatus.FILLED,
            filled_quantity=100,
        )
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.CANCELED,
            timestamp=datetime(2026, 1, 15, 11, 0, 0),
        )
        with pytest.raises(StateTransitionError, match="terminal state"):
            ticket.with_cancel(event)

    def test_with_reject(self) -> None:
        ticket = OrderTicket(order=_make_order())
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.REJECTED,
            timestamp=datetime(2026, 1, 15, 10, 30, 2),
            message="insufficient_buying_power",
        )
        new_ticket = ticket.with_reject(event)
        assert new_ticket.status == OrderStatus.REJECTED

    def test_with_invalid(self) -> None:
        """B2: can_retry=False → INVALID 终态"""
        ticket = OrderTicket(order=_make_order())
        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.INVALID,
            timestamp=datetime(2026, 1, 15, 10, 30, 2),
            message="[invalid] insufficient_auction",
        )
        new_ticket = ticket.with_invalid(event)
        assert new_ticket.status == OrderStatus.INVALID
        assert new_ticket.status.is_terminal


class TestOrderBook:
    def test_submit_and_get(self) -> None:
        book = OrderBook()
        ticket = OrderTicket(order=_make_order())
        book.submit(ticket)
        assert book.get("ORD-001") is ticket

    def test_get_nonexistent_returns_none(self) -> None:
        book = OrderBook()
        assert book.get("NONEXISTENT") is None

    def test_get_pending(self) -> None:
        book = OrderBook()
        book.submit(OrderTicket(order=_make_order("ORD-001")))
        book.submit(OrderTicket(order=_make_order("ORD-002")))

        pending = book.get_pending()
        assert len(pending) == 2

    def test_update_ticket(self) -> None:
        book = OrderBook()
        ticket = OrderTicket(order=_make_order())
        book.submit(ticket)

        event = OrderEvent(
            order_id="ORD-001",
            status=OrderStatus.SUBMITTED,
            timestamp=datetime(2026, 1, 15, 10, 30, 1),
        )
        submitted = replace(ticket, status=OrderStatus.SUBMITTED, order_events=(event,))
        book.update(submitted)

        assert book.get("ORD-001").status == OrderStatus.SUBMITTED

    def test_cancel_order(self) -> None:
        book = OrderBook()
        ticket = OrderTicket(order=_make_order())
        book.submit(ticket)
        book.cancel("ORD-001")
        assert book.get("ORD-001").status == OrderStatus.CANCELED

    def test_cancel_terminal_raises(self) -> None:
        book = OrderBook()
        filled = OrderTicket(
            order=_make_order(),
            status=OrderStatus.FILLED,
            filled_quantity=100,
        )
        book.submit(filled)
        with pytest.raises(StateTransitionError):
            book.cancel("ORD-001")

    def test_readonly_view(self) -> None:
        book = OrderBook()
        book.submit(OrderTicket(order=_make_order("ORD-001")))
        view = book.readonly_view()
        assert view.get("ORD-001") is not None
        assert len(view.get_pending()) == 1
