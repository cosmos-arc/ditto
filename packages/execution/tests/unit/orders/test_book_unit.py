"""T5: OrderBook + OrderBookReadOnly 单元测试。"""

from __future__ import annotations

import pytest
from ditto_execution.errors import OrderStateError
from ditto_execution.orders.book import OrderBook, OrderBookReadOnly
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


def _make_order(cid: str = "ord-1") -> Order:
    return Order(
        client_id=ClientOrderId(value=cid),
        instrument_id=InstrumentId(1),
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        quantity=100,
        price=10.0,
    )


def _make_event(
    cid: ClientOrderId, trigger: OrderTrigger, status: OrderStatus
) -> OrderEvent:
    return OrderEvent(client_id=cid, trigger=trigger, status=status)


# ---------------------------------------------------------------------------
# OrderBook
# ---------------------------------------------------------------------------


class TestOrderBookSubmit:
    def test_submit_creates_submitted_ticket(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        order = _make_order("sub-1")
        cid = order.client_id
        ticket = book.submit(order)

        assert ticket.status == OrderStatus.SUBMITTED
        assert book.get(cid) is ticket


class TestOrderBookUpdate:
    def test_update_replaces_ticket(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        order = _make_order("upd-1")
        cid = order.client_id
        original = book.submit(order)

        filled = original.with_fill(
            quantity=100,
            price=10.0,
            event=_make_event(cid, OrderTrigger.FILL, OrderStatus.FILLED),
        )
        book.update(filled)
        assert book.get(cid) is filled
        assert book.get(cid).status == OrderStatus.FILLED


class TestOrderBookCancel:
    def test_cancel_sets_canceled_and_appends_journal(self) -> None:
        journal = InMemoryOrderEventJournal()
        book = OrderBook(journal=journal)
        order = _make_order("can-1")
        cid = order.client_id
        book.submit(order)

        book.cancel(cid)
        assert book.get(cid).status == OrderStatus.CANCELED
        assert len(journal.events_for(cid)) == 2  # SUBMIT + CANCEL

    def test_cancel_unknown_raises(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        with pytest.raises(KeyError):
            book.cancel(ClientOrderId(value="ghost"))

    def test_cancel_terminal_raises(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        order = _make_order("can-term")
        cid = order.client_id
        ticket = book.submit(order)
        book.update(
            ticket.with_fill(
                quantity=100,
                price=10.0,
                event=_make_event(cid, OrderTrigger.FILL, OrderStatus.FILLED),
            )
        )
        with pytest.raises(OrderStateError):
            book.cancel(cid)


class TestOrderBookGetPending:
    def test_returns_non_terminal(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        o1 = _make_order("pen-1")
        o2 = _make_order("pen-2")
        book.submit(o1)
        ticket2 = book.submit(o2)

        # Fill o2 completely
        book.update(
            ticket2.with_fill(
                quantity=100,
                price=10.0,
                event=_make_event(o2.client_id, OrderTrigger.FILL, OrderStatus.FILLED),
            )
        )

        pending = book.get_pending()
        assert len(pending) == 1
        assert pending[0].order.client_id == o1.client_id

    def test_empty_book_returns_empty(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        assert book.get_pending() == ()


class TestOrderBookReadonlyView:
    def test_readonly_view_snapshot(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        order = _make_order("ro-1")
        cid = order.client_id
        book.submit(order)

        view = book.readonly_view()
        assert isinstance(view, OrderBookReadOnly)
        assert view.get(cid) is not None
        assert view.get(cid).status == OrderStatus.SUBMITTED

    def test_readonly_view_reflects_mutable_state(self) -> None:
        book = OrderBook(journal=InMemoryOrderEventJournal())
        view = book.readonly_view()
        assert view.get(ClientOrderId(value="nope")) is None
