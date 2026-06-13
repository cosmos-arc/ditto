"""BrokerGateway Protocol tests."""

from typing import Protocol, get_type_hints

import pytest
from ditto_execution.broker.contracts import (
    BROKER_GATEWAY_CONTRACT_VERSION,
    REQUIRED_BROKER_GATEWAY_CAPABILITIES,
    BrokerGateway,
    BrokerGatewayDescriptor,
    validate_broker_gateway_descriptor,
)
from ditto_execution.models import STANDARD_BROKER_EVENT_TYPES


def test_broker_gateway_is_protocol() -> None:
    assert issubclass(BrokerGateway, Protocol)


def test_broker_gateway_is_runtime_checkable() -> None:
    assert isinstance(42, BrokerGateway) is False


def test_broker_gateway_protocol_exposes_descriptor_contract() -> None:
    assert hasattr(BrokerGateway, "describe")
    assert get_type_hints(BrokerGateway.describe)["return"] is BrokerGatewayDescriptor


def test_broker_gateway_descriptor_accepts_required_capabilities_and_events() -> None:
    descriptor = BrokerGatewayDescriptor(
        gateway_id="paper",
        mode="paper",
        capabilities=REQUIRED_BROKER_GATEWAY_CAPABILITIES,
        supported_event_types=STANDARD_BROKER_EVENT_TYPES,
    )

    assert validate_broker_gateway_descriptor(descriptor) is descriptor
    assert descriptor.contract_version == BROKER_GATEWAY_CONTRACT_VERSION


def test_broker_gateway_descriptor_rejects_missing_required_capabilities() -> None:
    descriptor = BrokerGatewayDescriptor(
        gateway_id="paper",
        mode="paper",
        capabilities=frozenset({"connect"}),
        supported_event_types=STANDARD_BROKER_EVENT_TYPES,
    )

    with pytest.raises(ValueError, match="missing required capabilities"):
        validate_broker_gateway_descriptor(descriptor)


def test_broker_gateway_descriptor_rejects_unknown_event_types() -> None:
    descriptor = BrokerGatewayDescriptor(
        gateway_id="paper",
        mode="paper",
        capabilities=REQUIRED_BROKER_GATEWAY_CAPABILITIES,
        supported_event_types=("connect", "custom_callback"),
    )

    with pytest.raises(ValueError, match="Unsupported broker event type"):
        validate_broker_gateway_descriptor(descriptor)
