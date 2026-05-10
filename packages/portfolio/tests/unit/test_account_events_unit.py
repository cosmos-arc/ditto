"""Tests for Account event publishing via EventBus."""

from __future__ import annotations

from datetime import datetime

from ditto_kernel import DomainEvent
from ditto_kernel.events import EventName, SimpleEventBus
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.position import Position
from ditto_portfolio.events import PositionChanged

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fill(
    instrument_id: int = 1,
    direction: OrderSide = OrderSide.BUY,
    filled_quantity: int = 1000,
    fill_price: float = 10.5,
    fee: float = 5.0,
    fill_id: str = "fill-1",
    order_id: str = "ORD-001",
    event_time: datetime = datetime(2026, 3, 1, 15, 0),
) -> FillEvent:
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=0.0,
        event_time=event_time,
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
    )


def _make_position(
    instrument_id: int = 1,
    quantity: int = 1000,
    available_quantity: int = 1000,
    average_cost: float = 10.0,
) -> Position:
    return Position(
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=average_cost,
        market_value=average_cost * quantity,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAccountEventPublishing:
    """Account.apply_fill() 在有 event_bus 时发布 PositionChanged 事件."""

    def test_buy_publishes_position_changed(self) -> None:
        """BUY: apply_fill 应发布 PositionChanged 事件."""
        bus = SimpleEventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventName.POSITION_CHANGED, received.append)

        account = Account(
            cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
            event_bus=bus,
        )
        fill = _make_fill(filled_quantity=500, fill_price=10.0)

        account.apply_fill(fill, settle_date="2026-03-02")

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, PositionChanged)
        assert event.instrument_id == 1
        assert event.quantity_change == 500.0
        assert event.new_quantity == 500.0

    def test_sell_publishes_position_changed(self) -> None:
        """SELL: quantity_change 为负数, new_quantity 为剩余持仓."""
        bus = SimpleEventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventName.POSITION_CHANGED, received.append)

        account = Account(
            cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
            positions={1: _make_position(quantity=1000)},
            event_bus=bus,
        )
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=400,
            fill_price=12.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, PositionChanged)
        assert event.instrument_id == 1
        assert event.quantity_change == -400.0
        assert event.new_quantity == 600.0

    def test_sell_full_exit_publishes_zero_quantity(self) -> None:
        """SELL 全部卖出: new_quantity 为 0."""
        bus = SimpleEventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventName.POSITION_CHANGED, received.append)

        account = Account(
            cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
            positions={1: _make_position(quantity=1000)},
            event_bus=bus,
        )
        fill = _make_fill(
            direction=OrderSide.SELL,
            filled_quantity=1000,
            fill_price=11.0,
        )

        account.apply_fill(fill, settle_date="2026-03-02")

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, PositionChanged)
        assert event.quantity_change == -1000.0
        assert event.new_quantity == 0.0

    def test_event_timestamp_matches_fill_event_time(self) -> None:
        """事件时间戳应与 fill.event_time 一致."""
        bus = SimpleEventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventName.POSITION_CHANGED, received.append)

        account = Account(
            cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
            event_bus=bus,
        )
        event_time = datetime(2026, 5, 10, 14, 30)
        fill = _make_fill(event_time=event_time)

        account.apply_fill(fill, settle_date="2026-05-11")

        assert len(received) == 1
        assert received[0].timestamp == event_time

    def test_no_publish_when_event_bus_is_none(self) -> None:
        """event_bus=None 时不应发布任何事件（向后兼容）."""
        bus = SimpleEventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventName.POSITION_CHANGED, received.append)

        account = Account(
            cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
        )
        fill = _make_fill()

        account.apply_fill(fill, settle_date="2026-03-02")

        assert len(received) == 0

    def test_buy_adds_to_existing_position_publishes_total(self) -> None:
        """加仓: new_quantity 为加仓后总量."""
        bus = SimpleEventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventName.POSITION_CHANGED, received.append)

        account = Account(
            cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
            positions={1: _make_position(quantity=500, average_cost=10.0)},
            event_bus=bus,
        )
        fill = _make_fill(filled_quantity=300, fill_price=12.0)

        account.apply_fill(fill, settle_date="2026-03-02")

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, PositionChanged)
        assert event.quantity_change == 300.0
        assert event.new_quantity == 800.0
