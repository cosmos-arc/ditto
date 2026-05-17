"""T3: Order 模型 + OrderEvent + Journal Protocol 单元测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.orders.model import Order, OrderSide, OrderType
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client_order_id() -> ClientOrderId:
    return ClientOrderId.generate()


@pytest.fixture
def sample_order(client_order_id: ClientOrderId) -> Order:
    return Order(
        client_id=client_order_id,
        instrument_id=InstrumentId(1),
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        quantity=100,
        price=10.0,
    )


# ---------------------------------------------------------------------------
# Order model
# ---------------------------------------------------------------------------


class TestOrder:
    def test_frozen(self, sample_order: Order) -> None:
        with pytest.raises(FrozenInstanceError):
            sample_order.quantity = 200  # type: ignore[misc]

    def test_market_order_has_no_price(self, client_order_id: ClientOrderId) -> None:
        order = Order(
            client_id=client_order_id,
            instrument_id=InstrumentId(2),
            order_type=OrderType.MARKET,
            direction=OrderSide.SELL,
            quantity=200,
        )
        assert order.price is None

    def test_order_type_enum(self) -> None:
        assert len(OrderType) >= 3

    def test_order_direction_enum(self) -> None:
        assert len(OrderSide) == 2


# ---------------------------------------------------------------------------
# OrderEvent
# ---------------------------------------------------------------------------


class TestOrderEvent:
    def test_frozen(self, client_order_id: ClientOrderId) -> None:
        event = OrderEvent(
            client_id=client_order_id,
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=10.0,
            fill_quantity=100,
        )
        with pytest.raises(FrozenInstanceError):
            event.fill_price = 0.0  # type: ignore[misc]

    def test_contains_trigger(self, client_order_id: ClientOrderId) -> None:
        event = OrderEvent(
            client_id=client_order_id,
            trigger=OrderTrigger.CANCEL,
            status=OrderStatus.CANCELED,
        )
        assert event.trigger == OrderTrigger.CANCEL


# ---------------------------------------------------------------------------
# InMemoryOrderEventJournal
# ---------------------------------------------------------------------------


class TestInMemoryOrderEventJournal:
    def test_append_and_events_for(
        self,
        client_order_id: ClientOrderId,
    ) -> None:
        journal = InMemoryOrderEventJournal()
        event = OrderEvent(
            client_id=client_order_id,
            trigger=OrderTrigger.SUBMIT,
            status=OrderStatus.SUBMITTED,
        )
        journal.append(event)
        events = journal.events_for(client_order_id)
        assert len(events) == 1
        assert events[0] == event

    def test_events_for_unknown_id_returns_empty(
        self,
    ) -> None:
        journal = InMemoryOrderEventJournal()
        unknown = ClientOrderId(value="unknown")
        assert journal.events_for(unknown) == ()

    def test_all_events(self, client_order_id: ClientOrderId) -> None:
        journal = InMemoryOrderEventJournal()
        e1 = OrderEvent(
            client_id=client_order_id,
            trigger=OrderTrigger.SUBMIT,
            status=OrderStatus.SUBMITTED,
        )
        e2 = OrderEvent(
            client_id=client_order_id,
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=10.0,
            fill_quantity=100,
        )
        journal.append(e1)
        journal.append(e2)
        assert journal.all_events() == (e1, e2)

    def test_multiple_orders(self) -> None:
        journal = InMemoryOrderEventJournal()
        id_a = ClientOrderId(value="a")
        id_b = ClientOrderId(value="b")
        ea = OrderEvent(
            client_id=id_a, trigger=OrderTrigger.SUBMIT, status=OrderStatus.SUBMITTED
        )
        eb = OrderEvent(
            client_id=id_b, trigger=OrderTrigger.SUBMIT, status=OrderStatus.SUBMITTED
        )
        journal.append(ea)
        journal.append(eb)
        assert len(journal.events_for(id_a)) == 1
        assert len(journal.events_for(id_b)) == 1
        assert len(journal.all_events()) == 2
