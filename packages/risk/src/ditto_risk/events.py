"""Risk domain events — risk guard events."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_kernel import DomainEvent
from ditto_kernel.events import EventName

from ditto_risk.post_trade import RiskSeverity

__all__ = [
    "RiskGuardDetails",
    "RiskGuardTriggered",
]


@dataclass(frozen=True)
class RiskGuardDetails:
    """风控触发详情 — 类型化的审计载荷 (RISK-P1-03)."""

    instrument_id: int | None = None
    current_value: float | None = None
    limit_value: float | None = None
    description: str = ""


@dataclass(frozen=True, kw_only=True)
class RiskGuardTriggered(DomainEvent):
    """风控触发事件."""

    event_type: str = field(default=EventName.RISK_GUARD_TRIGGERED, init=False)
    rule_name: str
    severity: RiskSeverity
    details: RiskGuardDetails = field(default_factory=RiskGuardDetails)
