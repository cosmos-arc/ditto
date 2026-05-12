"""T4: OrderTicket（集成 FSM）单元测试。"""

from __future__ import annotations

import pytest
from ditto_execution.errors import OrderStateError
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order, OrderSide, OrderType
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client_order_id() -> ClientOrderId:
    return ClientOrderId(value="test-order-001")


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


@pytest.fixture
def submitted_ticket(sample_order: Order) -> OrderTicket:
    return OrderTicket(order=sample_order, status=OrderStatus.SUBMITTED)


def _fill_event(cid: ClientOrderId, qty: int = 100, price: float = 10.0) -> OrderEvent:
    return OrderEvent(
        client_id=cid,
        trigger=OrderTrigger.FILL,
        status=OrderStatus.FILLED,
        fill_price=price,
        fill_quantity=qty,
    )


# ---------------------------------------------------------------------------
# with_fill
# ---------------------------------------------------------------------------


class TestWithFill:
    def test_complete_fill(self, submitted_ticket: OrderTicket) -> None:
        filled = submitted_ticket.with_fill(
            quantity=100,
            price=10.0,
            event=_fill_event(submitted_ticket.order.client_id),
        )
        assert filled.status == OrderStatus.FILLED
        assert filled.filled_quantity == 100
        assert filled.leaves_quantity == 0

    def test_partial_fill(self, submitted_ticket: OrderTicket) -> None:
        partial = submitted_ticket.with_fill(
            quantity=50,
            price=10.0,
            event=_fill_event(submitted_ticket.order.client_id, qty=50),
        )
        assert partial.status == OrderStatus.PARTIALLY_FILLED
        assert partial.filled_quantity == 50
        assert partial.leaves_quantity == 50

    def test_multiple_fills(self, submitted_ticket: OrderTicket) -> None:
        cid = submitted_ticket.order.client_id
        t1 = submitted_ticket.with_fill(
            quantity=30,
            price=10.0,
            event=_fill_event(cid, qty=30),
        )
        assert t1.status == OrderStatus.PARTIALLY_FILLED

        t2 = t1.with_fill(
            quantity=70,
            price=11.0,
            event=OrderEvent(
                client_id=cid,
                trigger=OrderTrigger.FILL,
                status=OrderStatus.FILLED,
                fill_price=11.0,
                fill_quantity=70,
            ),
        )
        assert t2.status == OrderStatus.FILLED
        assert t2.filled_quantity == 100

    def test_average_fill_price(self, submitted_ticket: OrderTicket) -> None:
        cid = submitted_ticket.order.client_id
        t1 = submitted_ticket.with_fill(
            quantity=50,
            price=10.0,
            event=_fill_event(cid, qty=50),
        )
        assert t1.average_fill_price == 10.0

        t2 = t1.with_fill(
            quantity=50,
            price=12.0,
            event=OrderEvent(
                client_id=cid,
                trigger=OrderTrigger.FILL,
                status=OrderStatus.FILLED,
                fill_price=12.0,
                fill_quantity=50,
            ),
        )
        # VWAP: (10*50 + 12*50) / 100 = 11.0
        assert t2.average_fill_price == 11.0


# ---------------------------------------------------------------------------
# with_cancel / with_reject / with_invalid
# ---------------------------------------------------------------------------


class TestWithCancel:
    def test_cancel_submitted(self, submitted_ticket: OrderTicket) -> None:
        cid = submitted_ticket.order.client_id
        event = OrderEvent(
            client_id=cid,
            trigger=OrderTrigger.CANCEL,
            status=OrderStatus.CANCELED,
        )
        canceled = submitted_ticket.with_cancel(event)
        assert canceled.status == OrderStatus.CANCELED
        assert event in canceled.order_events

    def test_cancel_terminal_raises(self, sample_order: Order) -> None:
        cid = sample_order.client_id
        filled = OrderTicket(
            order=sample_order, status=OrderStatus.FILLED, filled_quantity=100
        )
        event = OrderEvent(
            client_id=cid,
            trigger=OrderTrigger.CANCEL,
            status=OrderStatus.CANCELED,
        )
        with pytest.raises(OrderStateError):
            filled.with_cancel(event)


class TestWithReject:
    def test_reject(self, submitted_ticket: OrderTicket) -> None:
        cid = submitted_ticket.order.client_id
        event = OrderEvent(
            client_id=cid,
            trigger=OrderTrigger.REJECT,
            status=OrderStatus.REJECTED,
        )
        rejected = submitted_ticket.with_reject(event)
        assert rejected.status == OrderStatus.REJECTED


class TestWithInvalid:
    def test_invalidate_new(self, sample_order: Order) -> None:
        cid = sample_order.client_id
        ticket = OrderTicket(order=sample_order, status=OrderStatus.NEW)
        event = OrderEvent(
            client_id=cid,
            trigger=OrderTrigger.INVALIDATE,
            status=OrderStatus.INVALID,
        )
        invalid = ticket.with_invalid(event)
        assert invalid.status == OrderStatus.INVALID

    def test_invalidate_terminal_raises(self, sample_order: Order) -> None:
        cid = sample_order.client_id
        filled = OrderTicket(
            order=sample_order, status=OrderStatus.FILLED, filled_quantity=100
        )
        event = OrderEvent(
            client_id=cid,
            trigger=OrderTrigger.INVALIDATE,
            status=OrderStatus.INVALID,
        )
        with pytest.raises(OrderStateError):
            filled.with_invalid(event)


# ---------------------------------------------------------------------------
# leaves_quantity
# ---------------------------------------------------------------------------


class TestLeavesQuantity:
    def test_initial(self, sample_order: Order) -> None:
        ticket = OrderTicket(order=sample_order, status=OrderStatus.NEW)
        assert ticket.leaves_quantity == 100

    def test_after_partial_fill(self, submitted_ticket: OrderTicket) -> None:
        cid = submitted_ticket.order.client_id
        partial = submitted_ticket.with_fill(
            quantity=30,
            price=10.0,
            event=_fill_event(cid, qty=30),
        )
        assert partial.leaves_quantity == 70


# ---------------------------------------------------------------------------
# order_events accumulation
# ---------------------------------------------------------------------------


class TestOrderEventsAccumulation:
    def test_events_auto_appended(self, submitted_ticket: OrderTicket) -> None:
        cid = submitted_ticket.order.client_id
        assert submitted_ticket.order_events == ()

        t1 = submitted_ticket.with_fill(
            quantity=50,
            price=10.0,
            event=_fill_event(cid, qty=50),
        )
        assert len(t1.order_events) == 1

        t2 = t1.with_fill(
            quantity=50,
            price=11.0,
            event=OrderEvent(
                client_id=cid,
                trigger=OrderTrigger.FILL,
                status=OrderStatus.FILLED,
                fill_price=11.0,
                fill_quantity=50,
            ),
        )
        assert len(t2.order_events) == 2


class TestWithFillValidation:
    """with_fill 参数校验。"""

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_rejects_non_positive_quantity(
        self,
        submitted_ticket: OrderTicket,
        quantity: int,
    ) -> None:
        cid = submitted_ticket.order.client_id
        event = _fill_event(cid)
        with pytest.raises(ValueError):
            submitted_ticket.with_fill(quantity=quantity, price=10.0, event=event)

    def test_rejects_overfill(self, submitted_ticket: OrderTicket) -> None:
        """with_fill(quantity > leaves_quantity) → ValueError。"""
        cid = submitted_ticket.order.client_id
        event = _fill_event(cid)
        with pytest.raises(ValueError, match="exceeds remaining"):
            submitted_ticket.with_fill(
                quantity=submitted_ticket.leaves_quantity + 1,
                price=10.0,
                event=event,
            )
