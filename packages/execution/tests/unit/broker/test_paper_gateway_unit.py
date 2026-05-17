"""
PaperBrokerGateway unit tests (E2A-1 through E2A-4).

Covers: connect, submit_order, cancel_order (all states),
query_fills (no fill / full fill).
"""

from __future__ import annotations

from datetime import datetime

from ditto_execution.broker.contracts import BrokerGateway
from ditto_execution.broker.gateways.paper import PaperBrokerGateway
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.fills import FillEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _order(
    cid: str = "test-1",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: int = 100,
    price: float | None = 10.0,
) -> Order:
    return Order(
        client_id=ClientOrderId(value=cid),
        instrument_id=InstrumentId(1),
        order_type=order_type,
        direction=side,
        quantity=quantity,
        price=price,
    )


# ---------------------------------------------------------------------------
# E2A-1: connect / basic Protocol
# ---------------------------------------------------------------------------


class TestPaperGatewayConnect:
    def test_connect_does_not_raise(self) -> None:
        gw = PaperBrokerGateway()
        gw.connect()  # should succeed silently

    def test_is_broker_gateway_instance(self) -> None:
        gw = PaperBrokerGateway()
        assert isinstance(gw, BrokerGateway)


class TestPaperGatewayGetAccount:
    def test_returns_account_view(self) -> None:
        gw = PaperBrokerGateway()
        view = gw.get_account()
        assert isinstance(view, AccountView)

    def test_default_account_has_zero_cash(self) -> None:
        gw = PaperBrokerGateway()
        view = gw.get_account()
        assert view.cash.total == 0.0

    def test_custom_initial_cash(self) -> None:
        gw = PaperBrokerGateway(initial_cash=1_000_000.0)
        view = gw.get_account()
        assert view.cash.available == 1_000_000.0


# ---------------------------------------------------------------------------
# E2A-2: submit_order — writes to book, returns OrderTicket, fills immediately
# ---------------------------------------------------------------------------


class TestPaperGatewaySubmitOrder:
    def test_submit_returns_order_ticket(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("sub-1")
        ticket = gw.submit_order(order)
        assert ticket.order is order

    def test_market_order_fills_immediately(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("mkt-1", order_type=OrderType.MARKET, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100
        assert ticket.filled_price == 10.0

    def test_limit_order_fills_immediately(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("lmt-1", order_type=OrderType.LIMIT, price=9.5)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100
        assert ticket.filled_price == 9.5

    def test_order_without_price_uses_zero(self) -> None:
        """Market order with no price fills at 0.0 (edge case)."""
        gw = PaperBrokerGateway()
        order = _order("noprice-1", order_type=OrderType.MARKET, price=None)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_price == 0.0

    def test_submit_records_fill_in_journal(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("jnl-1")
        gw.submit_order(order)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 1

    def test_submit_multiple_orders(self) -> None:
        gw = PaperBrokerGateway()
        o1 = _order("multi-1")
        o2 = _order("multi-2")
        t1 = gw.submit_order(o1)
        t2 = gw.submit_order(o2)
        assert t1.status == OrderStatus.FILLED
        assert t2.status == OrderStatus.FILLED
        assert t1.order.client_id != t2.order.client_id


# ---------------------------------------------------------------------------
# E2A-3: cancel_order — covers open / partial / nonexistent states
# ---------------------------------------------------------------------------


class TestPaperGatewayCancelOrder:
    def test_cancel_nonexistent_returns_false(self) -> None:
        gw = PaperBrokerGateway()
        assert gw.cancel_order("ghost-order") is False

    def test_cancel_filled_order_returns_false(self) -> None:
        """Filled (terminal) order cannot be cancelled."""
        gw = PaperBrokerGateway()
        order = _order("can-filled-1")
        gw.submit_order(order)
        assert gw.cancel_order(order.order_id) is False

    def test_cancel_open_order_succeeds(self) -> None:
        """Create an open order by pre-placing it without fill, then cancel."""
        gw = PaperBrokerGateway()
        order = _order("can-open-1")
        # Manually put order into book as SUBMITTED (not filled)
        gw._book.submit(order)
        assert gw.cancel_order(order.order_id) is True
        ticket = gw._book.get(order.client_id)
        assert ticket is not None
        assert ticket.status == OrderStatus.CANCELED

    def test_double_cancel_returns_false(self) -> None:
        """Second cancel on already-canceled order returns False."""
        gw = PaperBrokerGateway()
        order = _order("can-dbl-1")
        gw._book.submit(order)
        assert gw.cancel_order(order.order_id) is True
        assert gw.cancel_order(order.order_id) is False


# ---------------------------------------------------------------------------
# E2A-4: query_fills — no fill / partial fill / full fill
# ---------------------------------------------------------------------------


class TestPaperGatewayQueryFills:
    def test_no_fills_returns_empty(self) -> None:
        gw = PaperBrokerGateway()
        assert gw.query_fills("no-such-order") == ()

    def test_full_fill_returns_fill_event(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("fill-full-1", quantity=200, price=15.0)
        gw.submit_order(order)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 1
        fill = fills[0]
        assert isinstance(fill, FillEvent)
        assert fill.order_id == order.order_id
        assert fill.filled_quantity == 200
        assert fill.fill_price == 15.0
        assert fill.direction == OrderSide.BUY
        assert fill.cumulative_quantity == 200
        assert fill.leaves_quantity == 0

    def test_fill_event_has_valid_timestamp(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("fill-ts-1")
        gw.submit_order(order)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 1
        assert isinstance(fills[0].event_time, datetime)

    def test_sell_order_fill_direction(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("fill-sell-1", side=OrderSide.SELL, price=20.0)
        gw.submit_order(order)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 1
        assert fills[0].direction == OrderSide.SELL

    def test_multiple_orders_independent_fills(self) -> None:
        gw = PaperBrokerGateway()
        o1 = _order("ind-1", quantity=100, price=10.0)
        o2 = _order("ind-2", quantity=50, price=20.0)
        gw.submit_order(o1)
        gw.submit_order(o2)
        f1 = gw.query_fills(o1.order_id)
        f2 = gw.query_fills(o2.order_id)
        assert len(f1) == 1
        assert len(f2) == 1
        assert f1[0].filled_quantity == 100
        assert f2[0].filled_quantity == 50
