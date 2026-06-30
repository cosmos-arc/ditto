"""
PaperBrokerGateway conformance tests (B1A-5).

Complete behavior matrix: submit→fill, submit→cancel, submit→reject,
submit→partial_fill→fill. Each path verifies: OrderTicket status,
journal events, fills records, account changes.
"""

from __future__ import annotations

from ditto_execution.broker.gateways.paper import PaperBrokerGateway
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType


def _order(
    cid: str = "conf-1",
    quantity: int = 100,
    price: float | None = 10.0,
    instrument_id: int = 1,
) -> Order:
    return Order(
        client_id=ClientOrderId(value=cid),
        instrument_id=InstrumentId(instrument_id),
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        quantity=quantity,
        price=price,
    )


# ---------------------------------------------------------------------------
# Path 1: submit → full fill
# ---------------------------------------------------------------------------


class TestConformanceSubmitFill:
    def test_ticket_status_is_filled(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sf-1", quantity=100, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED

    def test_ticket_fill_quantities(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sf-2", quantity=200, price=5.0)
        ticket = gw.submit_order(order)
        assert ticket.filled_quantity == 200
        assert ticket.filled_price == 5.0
        assert ticket.average_fill_price == 5.0
        assert ticket.leaves_quantity == 0

    def test_journal_has_fill_event(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sf-3")
        gw.submit_order(order)
        events = gw._book._journal.events_for(order.client_id)
        fill_events = [e for e in events if e.trigger == OrderTrigger.FILL]
        assert len(fill_events) == 1
        assert fill_events[0].status == OrderStatus.FILLED

    def test_fills_recorded(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sf-4", quantity=100, price=10.0)
        gw.submit_order(order)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 1
        assert fills[0].filled_quantity == 100
        assert fills[0].fill_price == 10.0

    def test_account_cash_reduced(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("sf-5", quantity=100, price=10.0)
        gw.submit_order(order)
        view = gw.get_account()
        assert view.cash.available == 100_000.0 - 100 * 10.0

    def test_account_position_created(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("sf-6", quantity=100, price=10.0)
        gw.submit_order(order)
        view = gw.get_account()
        assert order.instrument_id in view.positions
        assert view.positions[order.instrument_id].quantity == 100


# ---------------------------------------------------------------------------
# Path 2: submit → cancel
# ---------------------------------------------------------------------------


class TestConformanceSubmitCancel:
    def test_ticket_status_is_canceled(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sc-1")
        gw._book.submit(order)
        gw.cancel_order(order.order_id)
        ticket = gw._book.get(order.client_id)
        assert ticket is not None
        assert ticket.status == OrderStatus.CANCELED

    def test_journal_has_cancel_event(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sc-2")
        gw._book.submit(order)
        gw.cancel_order(order.order_id)
        events = gw._book._journal.events_for(order.client_id)
        cancel_events = [e for e in events if e.trigger == OrderTrigger.CANCEL]
        assert len(cancel_events) == 1
        assert cancel_events[0].status == OrderStatus.CANCELED

    def test_no_fills_recorded(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sc-3")
        gw._book.submit(order)
        gw.cancel_order(order.order_id)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 0

    def test_account_unchanged(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("sc-4")
        gw._book.submit(order)
        gw.cancel_order(order.order_id)
        view = gw.get_account()
        assert view.cash.available == 100_000.0
        assert len(view.positions) == 0


# ---------------------------------------------------------------------------
# Path 3: submit → reject
# ---------------------------------------------------------------------------


class TestConformanceSubmitReject:
    def test_ticket_status_is_rejected(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sr-1")
        gw._book.submit(order)
        gw.reject_order(order.order_id, "risk limit")
        ticket = gw._book.get(order.client_id)
        assert ticket is not None
        assert ticket.status == OrderStatus.REJECTED

    def test_journal_has_reject_event_with_reason(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sr-2")
        gw._book.submit(order)
        gw.reject_order(order.order_id, "insufficient funds")
        events = gw._book._journal.events_for(order.client_id)
        reject_events = [e for e in events if e.trigger == OrderTrigger.REJECT]
        assert len(reject_events) == 1
        assert reject_events[0].status == OrderStatus.REJECTED
        assert reject_events[0].message == "insufficient funds"

    def test_no_fills_recorded(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("sr-3")
        gw._book.submit(order)
        gw.reject_order(order.order_id, "blocked")
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 0

    def test_account_unchanged(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("sr-4")
        gw._book.submit(order)
        gw.reject_order(order.order_id, "blocked")
        view = gw.get_account()
        assert view.cash.available == 100_000.0
        assert len(view.positions) == 0


# ---------------------------------------------------------------------------
# Path 4: submit → partial_fill → fill
# ---------------------------------------------------------------------------


class TestConformanceSubmitPartialFillFill:
    def test_partial_then_full_fill(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("spf-1", quantity=100, price=10.0)
        gw._book.submit(order)

        t1 = gw.simulate_fill(order.order_id, quantity=40, price=10.0)
        assert t1.status == OrderStatus.PARTIALLY_FILLED
        assert t1.filled_quantity == 40
        assert t1.leaves_quantity == 60

        t2 = gw.simulate_fill(order.order_id, quantity=60, price=10.5)
        assert t2.status == OrderStatus.FILLED
        assert t2.filled_quantity == 100
        assert t2.average_fill_price == 10.3

    def test_journal_has_both_fill_events(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("spf-2", quantity=100, price=10.0)
        gw._book.submit(order)
        gw.simulate_fill(order.order_id, quantity=40, price=10.0)
        gw.simulate_fill(order.order_id, quantity=60, price=10.5)

        events = gw._book._journal.events_for(order.client_id)
        fill_events = [e for e in events if e.trigger == OrderTrigger.FILL]
        assert len(fill_events) == 2
        assert fill_events[0].fill_quantity == 40
        assert fill_events[1].fill_quantity == 60

    def test_fills_accumulated(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("spf-3", quantity=100, price=10.0)
        gw._book.submit(order)
        gw.simulate_fill(order.order_id, quantity=40, price=10.0)
        gw.simulate_fill(order.order_id, quantity=60, price=10.5)

        fills = gw.query_fills(order.order_id)
        assert len(fills) == 2
        assert fills[0].filled_quantity == 40
        assert fills[1].filled_quantity == 60

    def test_partial_fill_reports_cumulative_and_leaves_quantities(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        order = _order("spf-5", quantity=100, price=10.0)
        gw._book.submit(order)
        gw.simulate_fill(order.order_id, quantity=40, price=10.0)
        gw.simulate_fill(order.order_id, quantity=60, price=10.5)

        fills = gw.query_fills(order.order_id)
        assert len(fills) == 2
        assert fills[0].filled_quantity == 40
        assert fills[0].cumulative_quantity == 40
        assert fills[0].leaves_quantity == 60
        assert fills[1].filled_quantity == 60
        assert fills[1].cumulative_quantity == 100
        assert fills[1].leaves_quantity == 0

    def test_account_reflects_total_fill(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("spf-4", quantity=100, price=10.0)
        gw._book.submit(order)
        gw.simulate_fill(order.order_id, quantity=40, price=10.0)
        gw.simulate_fill(order.order_id, quantity=60, price=10.5)

        view = gw.get_account()
        expected_cost = 40 * 10.0 + 60 * 10.5
        assert view.cash.available == 100_000.0 - expected_cost
        assert view.positions[order.instrument_id].quantity == 100
