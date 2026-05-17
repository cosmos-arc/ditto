"""
BrokerGateway Protocol conformance tests (E2A-5).

Reusable test suite that any BrokerGateway adapter must pass.
Import and call ``assert_gateway_conformance(MyGateway)`` to verify a new adapter.
"""

from __future__ import annotations

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
