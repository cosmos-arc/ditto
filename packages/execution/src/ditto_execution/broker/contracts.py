"""
Broker gateway contracts.

BrokerGateway is the low-level simulated broker-system gateway port for Paper.
It defines operations such as submit_order and
query_fills; simulation-time process_pending belongs to the runtime-facing
Brokerage port. The protocol defines the seam and does not implement real
broker adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_execution.models import (
    BrokerEventType,
    require_standard_broker_event_type,
)
from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket

__all__ = [
    "BROKER_GATEWAY_CONTRACT_VERSION",
    "REQUIRED_BROKER_GATEWAY_CAPABILITIES",
    "BrokerGateway",
    "BrokerGatewayCapability",
    "BrokerGatewayDescriptor",
    "BrokerGatewayMode",
    "validate_broker_gateway_descriptor",
]

BROKER_GATEWAY_CONTRACT_VERSION = "broker-gateway-v1"

type BrokerGatewayMode = Literal["paper", "recording"]
type BrokerGatewayCapability = Literal[
    "connect",
    "get_account",
    "submit_order",
    "cancel_order",
    "reject_order",
    "query_fills",
    "immediate_fill",
    "manual_fill_simulation",
    "event_recording",
    "broker_order_id_recovery",
]

REQUIRED_BROKER_GATEWAY_CAPABILITIES: frozenset[BrokerGatewayCapability] = frozenset(
    {
        "connect",
        "get_account",
        "submit_order",
        "cancel_order",
        "reject_order",
        "query_fills",
    }
)


@dataclass(frozen=True)
class BrokerGatewayDescriptor:
    """
    Stable capability descriptor every BrokerGateway implementation must expose.

    It is a protocol-level contract for Paper and its recording wrapper, not a
    real-broker integration point. Composition roots and conformance tests
    validate the descriptor before wiring an adapter into execution workflows.
    """

    gateway_id: str
    mode: BrokerGatewayMode
    capabilities: frozenset[BrokerGatewayCapability]
    supported_event_types: tuple[BrokerEventType, ...]
    contract_version: str = BROKER_GATEWAY_CONTRACT_VERSION
    notes: tuple[str, ...] = field(default_factory=tuple)


def validate_broker_gateway_descriptor(
    descriptor: BrokerGatewayDescriptor,
) -> BrokerGatewayDescriptor:
    """Validate a gateway descriptor and fail closed on protocol drift."""
    if not descriptor.gateway_id.strip():
        msg = "BrokerGatewayDescriptor.gateway_id must be non-empty"
        raise ValueError(msg)
    if descriptor.contract_version != BROKER_GATEWAY_CONTRACT_VERSION:
        msg = (
            f"Unsupported BrokerGateway contract version: {descriptor.contract_version}"
        )
        raise ValueError(msg)
    if descriptor.mode not in ("paper", "recording"):
        msg = f"Unsupported BrokerGateway mode: {descriptor.mode}"
        raise ValueError(msg)
    missing = REQUIRED_BROKER_GATEWAY_CAPABILITIES.difference(descriptor.capabilities)
    if missing:
        msg = "BrokerGatewayDescriptor missing required capabilities: "
        raise ValueError(msg + ", ".join(sorted(missing)))
    if not descriptor.supported_event_types:
        msg = "BrokerGatewayDescriptor.supported_event_types must be non-empty"
        raise ValueError(msg)
    for event_type in descriptor.supported_event_types:
        require_standard_broker_event_type(event_type)
    return descriptor


@runtime_checkable
class BrokerGateway(Protocol):
    """
    Simulated broker-system gateway port for Paper workflows.

    The gateway submits orders and queries broker fills. It does not own
    execution-loop pending-order processing, does not implement real broker
    adapters, and cannot represent one.
    """

    def describe(self) -> BrokerGatewayDescriptor:
        """Return adapter identity, contract version and capability descriptor."""
        ...

    def connect(self) -> None:
        """建立与券商系统的连接."""
        ...

    def get_account(self) -> AccountView:
        """获取当前账户状态快照."""
        ...

    def submit_order(self, order: Order) -> OrderTicket:
        """submit_order sends an order through the broker-system gateway port."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """取消已提交的订单，返回是否成功."""
        ...

    def reject_order(self, order_id: str, reason: str) -> bool:
        """拒绝订单并记录原因，返回是否成功."""
        ...

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        """query_fills returns broker-reported fills for an order."""
        ...
