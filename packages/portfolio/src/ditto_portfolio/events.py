"""Portfolio domain events — position change events."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_kernel import DomainEvent
from ditto_kernel.events import EventName
from ditto_kernel.identity import InstrumentId

__all__ = [
    "PositionChanged",
]


@dataclass(frozen=True, kw_only=True)
class PositionChanged(DomainEvent):
    """持仓变更事件 — Account.apply_fill 通过 event_bus 发布."""

    event_type: str = field(default=EventName.POSITION_CHANGED, init=False)
    instrument_id: InstrumentId
    quantity_change: int
    new_quantity: int
