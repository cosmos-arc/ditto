"""Produce and persist one typed Daily Decision V3 risk projection."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from ditto_features.risk_estimation.factor_risk import FactorRiskResult
from ditto_risk.analytics import StressTestReport, TailRiskReport

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.portfolio.construction import (
    PortfolioConstructionDecision,
)
from ditto_application.processes.risk.persistence import (
    DailyRiskProjectionRecord,
    RiskPersistencePort,
)
from ditto_application.processes.risk.reconciliation import ReconciliationReport
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3Projection,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)

__all__ = [
    "DailyRiskProjectionInput",
    "DailyRiskProjectionProcess",
    "ReconciliationAlertPort",
]


class ReconciliationAlertPort(Protocol):
    """Send a reconciliation alert using the report's idempotency key."""

    def send(self, report: ReconciliationReport) -> None:
        """Send or recognize an idempotent replay of one mismatch alert."""
        ...


@dataclass(frozen=True)
class DailyRiskProjectionInput:
    """Typed results and provenance needed for one V3 projection."""

    strategy_id: str
    account_id: str
    sleeve_id: str
    trade_date: str
    portfolio_construction: PortfolioConstructionDecision
    portfolio_duration_ms: float | None
    tail_risk: TailRiskReport
    factor_risk: FactorRiskResult | None
    requires_stock_factor_risk: bool
    stress_tests: StressTestReport
    reconciliation: ReconciliationReport
    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    generated_at: datetime


class DailyRiskProjectionProcess:
    """Assemble V3 evidence, alert on mismatch, and persist append-only output."""

    def __init__(
        self,
        *,
        persistence: RiskPersistencePort,
        reconciliation_alert: ReconciliationAlertPort | None = None,
    ) -> None:
        self._persistence = persistence
        self._reconciliation_alert = reconciliation_alert

    def build_and_persist(
        self,
        input_: DailyRiskProjectionInput,
    ) -> DailyDecisionV3Projection:
        """Build and append a projection without mutating authoritative books."""
        _validate_input(input_)
        projection = _build_projection(input_)
        if input_.reconciliation.status != "reconciled":
            alert = self._reconciliation_alert
            if alert is None:
                raise AppProcessError(
                    "reconciliation mismatch requires an idempotent alert port"
                )
            alert.send(input_.reconciliation)
        self._persistence.append_daily_report(
            DailyRiskProjectionRecord(
                report_id=_report_id(input_),
                strategy_id=input_.strategy_id,
                account_id=input_.account_id,
                sleeve_id=input_.sleeve_id,
                trade_date=input_.trade_date,
                projection=projection,
                created_at=input_.generated_at.isoformat(),
            )
        )
        return projection


def _build_projection(input_: DailyRiskProjectionInput) -> DailyDecisionV3Projection:
    construction = input_.portfolio_construction
    evidence = construction.evidence
    mode = _optional_string(evidence, "mode")
    construction_status = (
        "legacy" if construction.success and mode == "legacy" else "optimal"
    )
    blocking: list[str] = []
    if not construction.success:
        construction_status = "failed"
        blocking.append(construction.failure_code or "PORTFOLIO_CONSTRUCTION_FAILED")
    factor = input_.factor_risk
    if factor is None:
        factor_section = FactorRiskSection(
            availability="unavailable",
            total_risk=None,
            marginal_contributions={},
            percentage_contributions={},
            euler_residual=None,
        )
        if input_.requires_stock_factor_risk:
            blocking.append("STOCK_FACTOR_RISK_UNAVAILABLE")
    else:
        factor_section = FactorRiskSection(
            availability=factor.availability,
            total_risk=factor.total_risk,
            marginal_contributions=factor.marginal_contributions,
            percentage_contributions=factor.percentage_contributions,
            euler_residual=factor.euler_residual,
        )
        if input_.requires_stock_factor_risk and factor.stock_weight <= 0.0:
            blocking.append("STOCK_FACTOR_RISK_UNAVAILABLE")
    reconciliation = input_.reconciliation
    if reconciliation.status != "reconciled":
        blocking.append("RECONCILIATION_MISMATCH")
    return DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(
            status=construction_status,
            mode=mode,
            policy_digest=_optional_string(evidence, "policy_digest"),
            solver=_optional_string(evidence, "solver"),
            solver_version=_optional_string(evidence, "solver_version"),
            solver_status=_optional_string(evidence, "solver_status"),
            duration_ms=input_.portfolio_duration_ms,
            failure_code=construction.failure_code,
        ),
        tail_risk=TailRiskSection(
            historical_es99=input_.tail_risk.historical_es,
            historical_var99=input_.tail_risk.historical_var,
            parametric_var99=input_.tail_risk.parametric_var,
            monte_carlo_var99=input_.tail_risk.monte_carlo_var,
            monte_carlo_seed=input_.tail_risk.monte_carlo_seed,
        ),
        factor_risk=factor_section,
        stress_tests=StressTestSection(
            catalog_version=input_.stress_tests.catalog_version,
            losses=input_.stress_tests.losses,
            unavailable_scenarios=input_.stress_tests.unavailable_scenarios,
        ),
        reconciliation=ReconciliationSection(
            status=reconciliation.status,
            differences=reconciliation.differences,
            alert_idempotency_key=reconciliation.alert_idempotency_key,
        ),
        provenance=ProvenanceSection(
            decision_time=input_.decision_time.isoformat(),
            knowledge_cutoff=input_.knowledge_cutoff.isoformat(),
            publication_cutoff=input_.publication_cutoff.isoformat(),
            source_snapshot_ids=input_.source_snapshot_ids,
            generated_at=input_.generated_at.isoformat(),
        ),
        blocking_reasons=tuple(dict.fromkeys(blocking)),
    )


def _validate_input(input_: DailyRiskProjectionInput) -> None:
    identities = (
        input_.strategy_id,
        input_.account_id,
        input_.sleeve_id,
        input_.trade_date,
    )
    if any(not value.strip() for value in identities):
        raise AppProcessError("V3 projection identity must be complete")
    if (
        not input_.source_snapshot_ids
        or any(not value.strip() for value in input_.source_snapshot_ids)
        or len(set(input_.source_snapshot_ids)) != len(input_.source_snapshot_ids)
    ):
        raise AppProcessError("V3 projection requires unique source snapshots")
    if input_.knowledge_cutoff > input_.decision_time:
        raise AppProcessError("knowledge cutoff cannot follow decision time")
    if input_.publication_cutoff > input_.decision_time:
        raise AppProcessError("publication cutoff cannot follow decision time")
    duration = input_.portfolio_duration_ms
    if duration is not None and (not math.isfinite(duration) or duration < 0.0):
        raise AppProcessError("portfolio duration must be finite and non-negative")
    reconciliation = input_.reconciliation
    if (
        reconciliation.account_id != input_.account_id
        or reconciliation.sleeve_id != input_.sleeve_id
        or reconciliation.trade_date != input_.trade_date
    ):
        raise AppProcessError("reconciliation identity does not match projection")
    if (
        reconciliation.status != "reconciled"
        and not reconciliation.alert_idempotency_key
    ):
        raise AppProcessError(
            "reconciliation mismatch requires an alert idempotency key"
        )


def _optional_string(evidence: Mapping[str, object], key: str) -> str | None:
    value = evidence.get(key)
    return value if isinstance(value, str) and value else None


def _report_id(input_: DailyRiskProjectionInput) -> str:
    payload = "|".join(
        (
            input_.strategy_id,
            input_.account_id,
            input_.sleeve_id,
            input_.trade_date,
            input_.generated_at.isoformat(),
            *input_.source_snapshot_ids,
        )
    )
    return f"r4-v3:{sha256(payload.encode()).hexdigest()}"
