"""ditto_engine.events 单元测试."""

from datetime import datetime

import pytest
from ditto_engine.events import (
    OrderCanceled,
    OrderFilled,
    OrderSubmitted,
    PositionChanged,
    RiskGuardTriggered,
)


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
        from ditto_kernel import DomainEvent

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


class TestPositionChanged:
    def test_creation(self) -> None:
        event = PositionChanged(
            timestamp=datetime(2024, 1, 15, 15, 0),
            instrument_id=600000,
            quantity_change=100.0,
            new_quantity=200.0,
        )
        assert event.event_type == "position_changed"
        assert event.new_quantity == 200.0


class TestRiskGuardTriggered:
    def test_creation(self) -> None:
        event = RiskGuardTriggered(
            timestamp=datetime(2024, 1, 15, 14, 0),
            rule_name="max_drawdown",
            severity="critical",
        )
        assert event.event_type == "risk_guard_triggered"
        assert event.severity == "critical"
        assert event.details == {}

    def test_with_details(self) -> None:
        event = RiskGuardTriggered(
            timestamp=datetime(2024, 1, 15),
            rule_name="concentration_limit",
            severity="warning",
            details={"current": 0.35, "limit": 0.30},
        )
        assert event.details["current"] == 0.35
