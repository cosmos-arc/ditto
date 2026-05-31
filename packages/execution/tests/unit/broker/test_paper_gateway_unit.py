"""
PaperBrokerGateway unit tests.

Covers: connect, submit_order, cancel_order, reject_order,
query_fills, last_prices, simulate_fill.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest
from ditto_execution.broker.contracts import BrokerGateway
from ditto_execution.broker.gateways.paper import PaperBrokerGateway
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger
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
    instrument_id: int = 1,
) -> Order:
    return Order(
        client_id=ClientOrderId(value=cid),
        instrument_id=InstrumentId(instrument_id),
        order_type=order_type,
        direction=side,
        quantity=quantity,
        price=price,
    )


# ---------------------------------------------------------------------------
# connect / basic Protocol
# ---------------------------------------------------------------------------


class TestPaperGatewayConnect:
    def test_connect_does_not_raise(self) -> None:
        gw = PaperBrokerGateway()
        gw.connect()

    def test_is_broker_gateway_instance(self) -> None:
        gw = PaperBrokerGateway()
        assert isinstance(gw, BrokerGateway)


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------


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

    def test_buy_reduces_cash(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        gw.submit_order(_order("buy-cash-1", quantity=100, price=10.0))
        view = gw.get_account()
        assert view.cash.available == 100_000.0 - 100 * 10.0

    def test_sell_increases_cash(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        gw.submit_order(
            _order("sell-cash-1", side=OrderSide.BUY, quantity=100, price=10.0),
        )
        gw.submit_order(
            _order("sell-cash-2", side=OrderSide.SELL, quantity=100, price=12.0),
        )
        view = gw.get_account()
        assert view.cash.available == 100_000.0 - 100 * 10.0 + 100 * 12.0

    def test_buy_creates_position(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("pos-1", quantity=200, price=5.0)
        gw.submit_order(order)
        view = gw.get_account()
        assert order.instrument_id in view.positions
        pos = view.positions[order.instrument_id]
        assert pos.quantity == 200
        assert pos.average_cost == 5.0

    def test_sell_removes_position_when_flat(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("flat-1", quantity=100, price=10.0)
        gw.submit_order(order)
        gw.submit_order(
            _order("flat-2", side=OrderSide.SELL, quantity=100, price=11.0),
        )
        view = gw.get_account()
        assert order.instrument_id not in view.positions


# ---------------------------------------------------------------------------
# submit_order — fill price resolution
# ---------------------------------------------------------------------------


class TestPaperGatewaySubmitOrder:
    def test_submit_returns_order_ticket(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("sub-1")
        ticket = gw.submit_order(order)
        assert ticket.order is order

    def test_market_order_fills_immediately(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("mkt-1", order_type=OrderType.MARKET, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100
        assert ticket.filled_price == 10.0

    def test_limit_order_fills_immediately(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("lmt-1", order_type=OrderType.LIMIT, price=9.5)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100
        assert ticket.filled_price == 9.5

    def test_market_order_without_price_uses_last_prices(self) -> None:
        """Market order with no price uses last_prices lookup."""
        gw = PaperBrokerGateway(
            initial_cash=100_000.0,
            last_prices={InstrumentId(1): 4.56},
        )
        order = _order("lp-1", order_type=OrderType.MARKET, price=None)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_price == 4.56

    def test_market_order_without_price_nor_last_prices_warns(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Market order with no price and no last_prices → warning + 0.0."""
        gw = PaperBrokerGateway()
        order = _order("warn-1", order_type=OrderType.MARKET, price=None)
        with caplog.at_level(logging.WARNING):
            ticket = gw.submit_order(order)
        assert ticket.filled_price == 0.0
        assert "no last price" in caplog.text

    def test_limit_order_not_affected_by_last_prices(self) -> None:
        """Limit order fill price is the order price, not last_prices."""
        gw = PaperBrokerGateway(
            initial_cash=100_000.0,
            last_prices={InstrumentId(1): 99.0},
        )
        order = _order("lp-lmt-1", order_type=OrderType.LIMIT, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.filled_price == 10.0

    def test_submit_records_fill_in_journal(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("jnl-1")
        gw.submit_order(order)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 1

    def test_submit_multiple_orders(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        o1 = _order("multi-1")
        o2 = _order("multi-2")
        t1 = gw.submit_order(o1)
        t2 = gw.submit_order(o2)
        assert t1.status == OrderStatus.FILLED
        assert t2.status == OrderStatus.FILLED
        assert t1.order.client_id != t2.order.client_id


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


class TestPaperGatewayCancelOrder:
    def test_cancel_nonexistent_returns_false(self) -> None:
        gw = PaperBrokerGateway()
        assert gw.cancel_order("ghost-order") is False

    def test_cancel_filled_order_returns_false(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("can-filled-1")
        gw.submit_order(order)
        assert gw.cancel_order(order.order_id) is False

    def test_cancel_submitted_order_records_journal_event(self) -> None:
        """Cancel on SUBMITTED order → CANCELED status + journal has event."""
        gw = PaperBrokerGateway()
        order = _order("can-jnl-1")
        gw._book.submit(order)
        assert gw.cancel_order(order.order_id) is True

        ticket = gw._book.get(order.client_id)
        assert ticket is not None
        assert ticket.status == OrderStatus.CANCELED

        cancel_events = [
            e for e in ticket.order_events if e.trigger == OrderTrigger.CANCEL
        ]
        assert len(cancel_events) == 1
        assert cancel_events[0].status == OrderStatus.CANCELED

    def test_double_cancel_returns_false(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("can-dbl-1")
        gw._book.submit(order)
        assert gw.cancel_order(order.order_id) is True
        assert gw.cancel_order(order.order_id) is False


# ---------------------------------------------------------------------------
# reject_order
# ---------------------------------------------------------------------------


class TestPaperGatewayRejectOrder:
    def test_reject_submitted_order_succeeds(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("rej-1")
        gw._book.submit(order)
        assert gw.reject_order(order.order_id, "insufficient margin") is True

        ticket = gw._book.get(order.client_id)
        assert ticket is not None
        assert ticket.status == OrderStatus.REJECTED

    def test_reject_records_reason_in_event(self) -> None:
        gw = PaperBrokerGateway()
        order = _order("rej-reason-1")
        gw._book.submit(order)
        gw.reject_order(order.order_id, "risk limit exceeded")

        ticket = gw._book.get(order.client_id)
        assert ticket is not None
        reject_events = [
            e for e in ticket.order_events if e.trigger == OrderTrigger.REJECT
        ]
        assert len(reject_events) == 1
        assert reject_events[0].message == "risk limit exceeded"
        assert reject_events[0].status == OrderStatus.REJECTED

    def test_reject_nonexistent_returns_false(self) -> None:
        gw = PaperBrokerGateway()
        assert gw.reject_order("ghost", "no reason") is False

    def test_reject_filled_order_returns_false(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("rej-filled-1")
        gw.submit_order(order)
        assert gw.reject_order(order.order_id, "too late") is False


# ---------------------------------------------------------------------------
# simulate_fill — partial fill support
# ---------------------------------------------------------------------------


class TestPaperGatewaySimulateFill:
    def test_partial_fill_transitions_to_partially_filled(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("pf-1", quantity=100, price=10.0)
        gw._book.submit(order)

        ticket = gw.simulate_fill(order.order_id, quantity=50, price=10.0)
        assert ticket.status == OrderStatus.PARTIALLY_FILLED
        assert ticket.filled_quantity == 50
        assert ticket.leaves_quantity == 50

    def test_subsequent_fill_completes_order(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("pf-full-1", quantity=100, price=10.0)
        gw._book.submit(order)

        gw.simulate_fill(order.order_id, quantity=50, price=10.0)
        ticket = gw.simulate_fill(order.order_id, quantity=50, price=10.5)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100
        assert ticket.average_fill_price == 10.25

    def test_partial_fill_records_fill_event(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("pf-ev-1", quantity=100, price=10.0)
        gw._book.submit(order)

        gw.simulate_fill(order.order_id, quantity=40, price=10.0)
        fills = gw.query_fills(order.order_id)
        assert len(fills) == 1
        assert fills[0].filled_quantity == 40

    def test_simulate_fill_nonexistent_raises(self) -> None:
        gw = PaperBrokerGateway()
        try:
            gw.simulate_fill("ghost", quantity=10, price=1.0)
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass


# ---------------------------------------------------------------------------
# OrderType FAK/FAB/GTD
# ---------------------------------------------------------------------------


class TestPaperGatewayOrderTypeDegradation:
    def test_fak_fills_like_limit(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("fak-1", order_type=OrderType.FAK, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_price == 10.0

    def test_fab_fills_like_limit(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("fab-1", order_type=OrderType.FAB, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_price == 10.0

    def test_gtd_fills_like_limit(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("gtd-1", order_type=OrderType.GTD, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_price == 10.0


# ---------------------------------------------------------------------------
# query_fills
# ---------------------------------------------------------------------------


class TestPaperGatewayQueryFills:
    def test_no_fills_returns_empty(self) -> None:
        gw = PaperBrokerGateway()
        assert gw.query_fills("no-such-order") == ()

    def test_full_fill_returns_fill_event(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
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
        gw = PaperBrokerGateway(initial_cash=100_000.0)
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
        gw = PaperBrokerGateway(initial_cash=100_000.0)
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


# ---------------------------------------------------------------------------
# B1B-3: RiskGate (OrderPreSubmitCheck) integration
# ---------------------------------------------------------------------------


class _AcceptAll:
    """Fake risk check that accepts all orders unchanged."""

    def pre_submit(self, order: Order) -> Order | None:
        return order


class _RejectAll:
    """Fake risk check that rejects all orders."""

    def pre_submit(self, order: Order) -> Order | None:
        return None


class _ResizeOrder:
    """Fake risk check that resizes order quantity to 50."""

    def pre_submit(self, order: Order) -> Order | None:
        return order.with_quantity(50)


class TestPaperGatewayRiskGate:
    def test_no_risk_check_unchanged_behavior(self) -> None:
        gw = PaperBrokerGateway(initial_cash=100_000.0)
        order = _order("no-risk-1", price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100

    def test_risk_check_accept_fills_normally(self) -> None:
        gw = PaperBrokerGateway(
            initial_cash=100_000.0,
            risk_check=_AcceptAll(),
        )
        order = _order("risk-accept-1", price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100

    def test_risk_check_reject_returns_rejected_ticket(self) -> None:
        gw = PaperBrokerGateway(
            initial_cash=100_000.0,
            risk_check=_RejectAll(),
        )
        order = _order("risk-reject-1", price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.REJECTED

    def test_risk_check_reject_records_journal_event(self) -> None:
        gw = PaperBrokerGateway(
            initial_cash=100_000.0,
            risk_check=_RejectAll(),
        )
        order = _order("risk-reject-jnl-1", price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.REJECTED
        reject_events = [
            e for e in ticket.order_events if e.trigger == OrderTrigger.REJECT
        ]
        assert len(reject_events) == 1
        assert "risk gate blocked" in (reject_events[0].message or "")

    def test_risk_check_reject_does_not_apply_fill(self) -> None:
        gw = PaperBrokerGateway(
            initial_cash=100_000.0,
            risk_check=_RejectAll(),
        )
        order = _order("risk-no-fill-1", price=10.0)
        gw.submit_order(order)
        view = gw.get_account()
        assert view.cash.available == 100_000.0

    def test_risk_check_resize_modifies_quantity(self) -> None:
        gw = PaperBrokerGateway(
            initial_cash=100_000.0,
            risk_check=_ResizeOrder(),
        )
        order = _order("risk-resize-1", quantity=100, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 50


# ---------------------------------------------------------------------------
# B4-4: InsufficientFundsError
# ---------------------------------------------------------------------------


class TestPaperGatewayInsufficientFunds:
    def test_buy_with_zero_cash_raises_insufficient_funds(self) -> None:
        """BUY order with zero cash raises InsufficientFundsError."""
        from ditto_execution.errors import InsufficientFundsError

        gw = PaperBrokerGateway()
        order = _order("no-cash-1", quantity=100, price=10.0)
        with pytest.raises(InsufficientFundsError, match="资金不足"):
            gw.submit_order(order)

    def test_buy_exceeding_cash_raises_insufficient_funds(self) -> None:
        """BUY order exceeding available cash raises InsufficientFundsError."""
        from ditto_execution.errors import InsufficientFundsError

        gw = PaperBrokerGateway(initial_cash=500.0)
        order = _order("over-cash-1", quantity=100, price=10.0)
        with pytest.raises(InsufficientFundsError, match="资金不足"):
            gw.submit_order(order)

    def test_sell_with_zero_cash_does_not_raise(self) -> None:
        """SELL order does not require cash — no InsufficientFundsError."""
        gw = PaperBrokerGateway()
        order = _order("sell-no-cash-1", side=OrderSide.SELL, price=10.0)
        ticket = gw.submit_order(order)
        assert ticket.status == OrderStatus.FILLED

    def test_insufficient_funds_error_is_order_submit_error(self) -> None:
        """InsufficientFundsError is a subclass of OrderSubmitError."""
        from ditto_execution.errors import InsufficientFundsError, OrderSubmitError

        assert issubclass(InsufficientFundsError, OrderSubmitError)
