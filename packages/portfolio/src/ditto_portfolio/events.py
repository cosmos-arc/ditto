"""Portfolio domain events — position change events."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_kernel import DomainEvent
from ditto_kernel.events import EventName

__all__ = [
    "PositionChanged",
]


@dataclass(frozen=True, kw_only=True)
class PositionChanged(DomainEvent):
    """持仓变更事件（预留 — 当前未在生产流程中发布）."""

    event_type: str = field(default=EventName.POSITION_CHANGED, init=False)
    instrument_id: int
    quantity_change: float
    new_quantity: float
