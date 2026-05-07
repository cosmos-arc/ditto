"""Risk domain events — risk guard events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ditto_kernel import DomainEvent

__all__ = [
    "RiskGuardTriggered",
]


@dataclass(frozen=True, kw_only=True)
class RiskGuardTriggered(DomainEvent):
    """风控触发事件."""

    event_type: str = field(default="risk_guard_triggered", init=False)
    rule_name: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)
