"""Execution package domain events unit tests."""

from datetime import datetime

import pytest
from ditto_execution.events import (
    OrderCanceled,
    OrderExpired,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
)
from ditto_kernel import DomainEvent
from ditto_kernel.events import EventName


class TestOrderSubmitted:
    def test_creation(self) -> None:
        event = OrderSubmitted(
            timestamp=datetime(2024, 1, 15, 9, 30),
            order_id="ORD-001",
            instrument_id=600000,
            side="BUY",
            quantity=100.0,
        )
        assert event.event_type == "order_submitted"
        assert event.order_id == "ORD-001"
        assert event.instrument_id == 600000
        assert event.side == "BUY"
        assert event.quantity == 100.0
        assert event.payload == {}

    def test_frozen(self) -> None:
        event = OrderSubmitted(
            timestamp=datetime(2024, 1, 15),
            order_id="ORD-001",
            instrument_id=600000,
            side="BUY",
            quantity=100.0,
        )
        with pytest.raises(AttributeError):
            event.order_id = "changed"  # type: ignore[misc]

    def test_inherits_domain_event(self) -> None:
        event = OrderSubmitted(
            timestamp=datetime(2024, 1, 15),
            order_id="ORD-001",
            instrument_id=600000,
            side="BUY",
            quantity=100.0,
        )
        assert isinstance(event, DomainEvent)


class TestOrderFilled:
    def test_creation(self) -> None:
        event = OrderFilled(
            timestamp=datetime(2024, 1, 15, 9, 30, 5),
            order_id="ORD-001",
            fill_price=10.5,
            filled_quantity=100.0,
        )
        assert event.event_type == "order_filled"
        assert event.fill_price == 10.5
        assert event.fee == 0.0

    def test_with_fee(self) -> None:
        event = OrderFilled(
            timestamp=datetime(2024, 1, 15),
            order_id="ORD-001",
            fill_price=10.5,
            filled_quantity=100.0,
            fee=5.25,
        )
        assert event.fee == 5.25


class TestOrderCanceled:
    def test_creation(self) -> None:
        event = OrderCanceled(
            timestamp=datetime(2024, 1, 15, 9, 30),
            order_id="ORD-001",
            reason="insufficient_funds",
        )
        assert event.event_type == "order_canceled"
        assert event.reason == "insufficient_funds"


class TestOrderRejected:
    def test_creation(self) -> None:
        event = OrderRejected(
            timestamp=datetime(2024, 1, 15, 9, 30),
            order_id="ORD-002",
            reason="invalid_price",
        )
        assert event.event_type == EventName.ORDER_REJECTED
        assert event.order_id == "ORD-002"
        assert event.reason == "invalid_price"
        assert isinstance(event, DomainEvent)

    def test_frozen(self) -> None:
        event = OrderRejected(
            timestamp=datetime(2024, 1, 15),
            order_id="ORD-002",
            reason="test",
        )
        with pytest.raises(AttributeError):
            event.reason = "changed"  # type: ignore[misc]


class TestOrderExpired:
    def test_creation(self) -> None:
        event = OrderExpired(
            timestamp=datetime(2024, 1, 15, 15, 0),
            order_id="ORD-003",
            reason="market_closed",
        )
        assert event.event_type == EventName.ORDER_EXPIRED
        assert event.order_id == "ORD-003"
        assert event.reason == "market_closed"
        assert isinstance(event, DomainEvent)
