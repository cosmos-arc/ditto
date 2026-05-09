"""Execution domain events — order lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_kernel import DomainEvent
from ditto_kernel.events import EventName

__all__ = [
    "OrderCanceled",
    "OrderFilled",
    "OrderSubmitted",
]


@dataclass(frozen=True, kw_only=True)
class OrderSubmitted(DomainEvent):
    """订单提交事件."""

    event_type: str = field(default=EventName.ORDER_SUBMITTED, init=False)
    order_id: str
    instrument_id: int
    side: str
    quantity: float


@dataclass(frozen=True, kw_only=True)
class OrderFilled(DomainEvent):
    """订单成交事件."""

    event_type: str = field(default=EventName.ORDER_FILLED, init=False)
    order_id: str
    fill_price: float
    filled_quantity: float
    fee: float = 0.0


@dataclass(frozen=True, kw_only=True)
class OrderCanceled(DomainEvent):
    """订单取消事件."""

    event_type: str = field(default=EventName.ORDER_CANCELED, init=False)
    order_id: str
    reason: str
