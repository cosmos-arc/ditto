"""Engine 领域事件 — 交易/风控相关事件子类."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ditto_kernel import DomainEvent

__all__ = [
    "OrderCanceled",
    "OrderFilled",
    "OrderSubmitted",
    "PositionChanged",
    "RiskGuardTriggered",
]


@dataclass(frozen=True, kw_only=True)
class OrderSubmitted(DomainEvent):
    """订单提交事件."""

    event_type: str = field(default="order_submitted", init=False)
    order_id: str
    instrument_id: int
    side: str
    quantity: float


@dataclass(frozen=True, kw_only=True)
class OrderFilled(DomainEvent):
    """订单成交事件."""

    event_type: str = field(default="order_filled", init=False)
    order_id: str
    fill_price: float
    filled_quantity: float
    fee: float = 0.0


@dataclass(frozen=True, kw_only=True)
class OrderCanceled(DomainEvent):
    """订单取消事件."""

    event_type: str = field(default="order_canceled", init=False)
    order_id: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class PositionChanged(DomainEvent):
    """持仓变更事件."""

    event_type: str = field(default="position_changed", init=False)
    instrument_id: int
    quantity_change: float
    new_quantity: float


@dataclass(frozen=True, kw_only=True)
class RiskGuardTriggered(DomainEvent):
    """风控触发事件."""

    event_type: str = field(default="risk_guard_triggered", init=False)
    rule_name: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)
