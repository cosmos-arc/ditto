"""Kill Switch — 实盘安全前置，三级熔断机制."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "KillSwitchDecision",
    "KillSwitchLevel",
]


class KillSwitchLevel(StrEnum):
    """Kill Switch 三级熔断级别."""

    ALERT_ONLY = "alert_only"
    HALT_NEW_ORDERS = "halt_new_orders"
    LIQUIDATE_ALL = "liquidate_all"


@dataclass(frozen=True)
class KillSwitchDecision:
    """Kill Switch 决策记录 — 可审计的风控熔断决策."""

    level: KillSwitchLevel
    reason: str
    triggered_at: str
    order_ids: tuple[str, ...] = ()
