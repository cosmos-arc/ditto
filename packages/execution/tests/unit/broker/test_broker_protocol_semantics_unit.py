"""Broker protocol semantic responsibility tests."""

import ditto_execution.brokerage as brokerage_module
import ditto_execution.models as execution_models
import pytest
from ditto_execution.broker.contracts import BrokerGateway
from ditto_execution.brokerage import Brokerage


def test_broker_protocols_have_non_overlapping_documented_responsibilities() -> None:
    assert hasattr(BrokerGateway, "submit_order")
    assert not hasattr(BrokerGateway, "process_pending")
    assert hasattr(Brokerage, "place_order")
    assert hasattr(Brokerage, "process_pending")

    gateway_docs = "\n".join(
        (
            BrokerGateway.__module__,
            BrokerGateway.__doc__ or "",
            BrokerGateway.submit_order.__doc__ or "",
            BrokerGateway.query_fills.__doc__ or "",
        )
    ).lower()
    brokerage_docs = "\n".join(
        (
            Brokerage.__module__,
            brokerage_module.__doc__ or "",
            Brokerage.__doc__ or "",
            Brokerage.place_order.__doc__ or "",
            Brokerage.process_pending.__doc__ or "",
        )
    ).lower()
    gateway_words = " ".join(gateway_docs.split())
    brokerage_words = " ".join(brokerage_docs.split())

    assert "broker-system gateway port" in gateway_words
    assert "does not implement real broker adapters" in gateway_words
    assert "submit_order" in gateway_docs
    assert "query_fills" in gateway_docs
    assert "runtime-facing" in brokerage_docs
    assert "backtest/live execution loops" in brokerage_docs
    assert "place_order" in brokerage_docs
    assert "process_pending" in brokerage_docs
    assert "execution/application wiring" in brokerage_docs
    assert "not in backtest" in brokerage_words


def test_standard_broker_event_taxonomy_is_explicit_and_validated() -> None:
    assert hasattr(execution_models, "STANDARD_BROKER_EVENT_TYPES")
    assert hasattr(execution_models, "require_standard_broker_event_type")
    assert execution_models.STANDARD_BROKER_EVENT_TYPES == (
        "connect",
        "order_ack",
        "fill",
        "fill_query_error",
        "cancel",
        "reject",
        "account_update",
    )
    assert execution_models.require_standard_broker_event_type("fill") == "fill"

    with pytest.raises(ValueError, match="Unsupported broker event type"):
        execution_models.require_standard_broker_event_type("custom_adapter_callback")
