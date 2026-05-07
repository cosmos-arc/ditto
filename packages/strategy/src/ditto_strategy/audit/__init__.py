"""Audit — 策略审计追踪。"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["StrategyAuditRecord"]


@dataclass(frozen=True)
class StrategyAuditRecord:
    """Strategy-owned decision trace record."""

    audit_id: str
    strategy_id: str
    run_id: str
    event_type: str
    occurred_at: str
    details: dict[str, object] = field(default_factory=dict)
