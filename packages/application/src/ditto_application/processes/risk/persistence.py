"""Application-owned persistence contracts for R4 risk state and reports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ditto_risk.continuous_gate import RiskStateSnapshot

from ditto_application.queries.daily_decision_v3 import DailyDecisionV3Projection

__all__ = [
    "DailyRiskProjectionRecord",
    "RiskEventRecord",
    "RiskPersistenceConflict",
    "RiskPersistencePort",
]


class RiskPersistenceConflict(RuntimeError):
    """Raised for event identity conflict or stale risk-state CAS."""


@dataclass(frozen=True)
class RiskEventRecord:
    """Append-only risk event persistence command."""

    event_id: str
    account_id: str
    sleeve_id: str
    event_sequence: int
    event_type: str
    payload: Mapping[str, object]
    occurred_at: str


@dataclass(frozen=True)
class DailyRiskProjectionRecord:
    """Append-only Daily Decision V3 risk projection command."""

    report_id: str
    strategy_id: str
    account_id: str
    sleeve_id: str
    trade_date: str
    projection: DailyDecisionV3Projection
    created_at: str


class RiskPersistencePort(Protocol):
    """Consumer-owned append/CAS persistence boundary."""

    def append_event(self, record: RiskEventRecord) -> bool:
        """Append a unique event; return False for an exact replay."""
        ...

    def compare_and_swap_snapshot(
        self,
        snapshot: RiskStateSnapshot,
        *,
        expected_event_sequence: int,
    ) -> None:
        """Append a snapshot only when latest sequence matches expectation."""
        ...

    def load_latest_snapshot(
        self,
        account_id: str,
        sleeve_id: str,
    ) -> RiskStateSnapshot | None:
        """Load the latest versioned snapshot for one state owner."""
        ...

    def append_daily_report(self, record: DailyRiskProjectionRecord) -> bool:
        """Append a report; return False for an exact replay."""
        ...
