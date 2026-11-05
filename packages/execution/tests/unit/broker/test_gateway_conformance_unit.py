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
        "describe",
        "connect",
        "get_account",
        "submit_order",
        "cancel_order",
        "reject_order",
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
# Conformance: BrokerEventRecordingGateway
# ---------------------------------------------------------------------------


def test_broker_event_recording_gateway_satisfies_broker_gateway_protocol() -> None:
    from ditto_execution.broker.recording import BrokerEventRecordingGateway

    assert_gateway_conformance(BrokerEventRecordingGateway)
