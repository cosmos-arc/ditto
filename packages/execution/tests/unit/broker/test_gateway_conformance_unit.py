"""
BrokerGateway Protocol conformance tests (E2A-5).

Reusable test suite that any BrokerGateway adapter must pass.
Import and call ``assert_gateway_conformance(MyGateway)`` to verify a new adapter.
"""

from __future__ import annotations

from typing import get_type_hints

from ditto_execution.broker.contracts import BrokerGateway


def assert_gateway_conformance(gateway_cls: type) -> None:
    """Verify *gateway_cls* satisfies the BrokerGateway Protocol contract."""
    assert issubclass(gateway_cls, BrokerGateway), (
        f"{gateway_cls.__name__} does not satisfy BrokerGateway Protocol"
    )
    # Every protocol method must be present as a concrete method.
    required = [
        "connect",
        "get_account",
        "submit_order",
        "cancel_order",
        "query_fills",
    ]
    for method_name in required:
        assert hasattr(gateway_cls, method_name), (
            f"{gateway_cls.__name__} missing method: {method_name}"
        )

    # Verify return-type annotations match the Protocol definition.
    for method_name in required:
        proto_method = getattr(BrokerGateway, method_name)
        proto_return = get_type_hints(proto_method).get("return")
        assert proto_return is not None, (
            f"BrokerGateway.{method_name} missing return annotation"
        )
        impl_method = getattr(gateway_cls, method_name)
        impl_return = get_type_hints(impl_method).get("return")
        assert impl_return == proto_return, (
            f"{gateway_cls.__name__}.{method_name} return type "
            f"{impl_return} != Protocol {proto_return}"
        )


# ---------------------------------------------------------------------------
# Conformance: PaperBrokerGateway
# ---------------------------------------------------------------------------


def test_paper_gateway_satisfies_broker_gateway_protocol() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    assert_gateway_conformance(PaperBrokerGateway)


def test_paper_gateway_instance_check() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    gw = PaperBrokerGateway()
    assert isinstance(gw, BrokerGateway)


# ---------------------------------------------------------------------------
# Instance behavior: PaperBrokerGateway
# ---------------------------------------------------------------------------


def test_paper_gateway_connect_does_not_raise() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    gw = PaperBrokerGateway()
    gw.connect()  # should not raise


def test_paper_gateway_submit_order_returns_ticket() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway
    from ditto_execution.orders.ids import ClientOrderId
    from ditto_execution.orders.model import Order
    from ditto_kernel.identity import InstrumentId
    from ditto_kernel.order import OrderSide, OrderType

    gw = PaperBrokerGateway()
    order = Order(
        client_id=ClientOrderId(value="test-001"),
        instrument_id=InstrumentId(510300),
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        quantity=100,
        price=4.50,
    )
    ticket = gw.submit_order(order)
    from ditto_execution.orders.ticket import OrderTicket

    assert isinstance(ticket, OrderTicket)


def test_paper_gateway_cancel_order_returns_bool() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    gw = PaperBrokerGateway()
    result = gw.cancel_order("nonexistent")
    assert isinstance(result, bool)
    assert result is False


def test_paper_gateway_query_fills_returns_tuple() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    gw = PaperBrokerGateway()
    fills = gw.query_fills("nonexistent")
    assert isinstance(fills, tuple)


def test_paper_gateway_get_account_returns_account_view() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway
    from ditto_portfolio.accounting.account import AccountView

    gw = PaperBrokerGateway()
    account = gw.get_account()
    assert isinstance(account, AccountView)
