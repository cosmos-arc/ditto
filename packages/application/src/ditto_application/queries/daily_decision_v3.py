"""Typed Daily Decision V3 report with R4 risk and reconciliation evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.daily_decision import DailyDecisionV2Report

__all__ = [
    "DailyDecisionV3Projection",
    "DailyDecisionV3ProjectionReader",
    "DailyDecisionV3QueryFacade",
    "DailyDecisionV3Report",
    "FactorRiskSection",
    "NullDailyDecisionV3ProjectionReader",
    "PortfolioConstructionSection",
    "ProvenanceSection",
    "ReconciliationSection",
    "StressTestSection",
    "TailRiskSection",
    "build_daily_decision_v3_report",
]


@dataclass(frozen=True)
class PortfolioConstructionSection:
    """Optimizer outcome and fixed-solver provenance."""

    status: str
    mode: str | None = None
    policy_digest: str | None = None
    solver: str | None = None
    solver_version: str | None = None
    solver_status: str | None = None
    duration_ms: float | None = None
    failure_code: str | None = None


@dataclass(frozen=True)
class TailRiskSection:
    """Positive-loss ES99 headline plus VaR diagnostics."""

    historical_es99: float | None
    historical_var99: float | None
    parametric_var99: float | None
    monte_carlo_var99: float | None
    monte_carlo_seed: int | None

    def __post_init__(self) -> None:
        """Enforce the headline ES/VaR relationship when values are available."""
        if (
            self.historical_es99 is not None
            and self.historical_var99 is not None
            and self.historical_es99 < self.historical_var99
        ):
            raise AppQueryError("Historical ES99 must be at least Historical VaR99")


@dataclass(frozen=True)
class FactorRiskSection:
    """Stock factor availability and Euler contribution evidence."""

    availability: str
    total_risk: float | None
    marginal_contributions: Mapping[str, float]
    percentage_contributions: Mapping[str, float]
    euler_residual: float | None


@dataclass(frozen=True)
class StressTestSection:
    """Versioned scenario catalog results using positive loss values."""

    catalog_version: str
    losses: Mapping[str, float]
    unavailable_scenarios: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationSection:
    """Three-layer EOD reconciliation readiness and alert identity."""

    status: str
    differences: tuple[str, ...]
    alert_idempotency_key: str | None


@dataclass(frozen=True)
class ProvenanceSection:
    """Complete temporal and source revision boundaries for the report."""

    decision_time: str | None
    knowledge_cutoff: str | None
    publication_cutoff: str | None
    source_snapshot_ids: tuple[str, ...]
    generated_at: str | None


@dataclass(frozen=True)
class DailyDecisionV3Projection:
    """Persisted R4 evidence projected independently of the legacy V2 model."""

    portfolio_construction: PortfolioConstructionSection
    tail_risk: TailRiskSection
    factor_risk: FactorRiskSection
    stress_tests: StressTestSection
    reconciliation: ReconciliationSection
    provenance: ProvenanceSection
    blocking_reasons: tuple[str, ...] = ()


class DailyDecisionV3ProjectionReader(Protocol):
    """Consumer-owned read port for persisted R4 daily evidence."""

    def get_latest(
        self,
        *,
        strategy_id: str,
        trade_date: str | None,
        account_id: str | None,
        sleeve_id: str | None,
    ) -> DailyDecisionV3Projection | None:
        """Read one exact strategy/date/account projection."""
        ...


class NullDailyDecisionV3ProjectionReader:
    """Fail-closed default used until apps binds a durable projection reader."""

    def get_latest(
        self,
        *,
        strategy_id: str,
        trade_date: str | None,
        account_id: str | None,
        sleeve_id: str | None,
    ) -> DailyDecisionV3Projection | None:
        """Return no evidence so V3 readiness is blocked by the query facade."""
        del strategy_id, trade_date, account_id, sleeve_id
        return None


class DailyDecisionV3QueryFacade:
    """Compose the unchanged V2 report with persisted R4 evidence."""

    def __init__(
        self,
        *,
        v2_facade: object,
        projection_reader: DailyDecisionV3ProjectionReader,
    ) -> None:
        """Store consumer facades without introducing storage details."""
        self._v2_facade = v2_facade
        self._projection_reader = projection_reader

    def get_report_v3(
        self,
        *,
        strategy_id: str,
        trade_date: str | None = None,
        account_id: str | None = None,
    ) -> DailyDecisionV3Report:
        """Read V2 and R4 projections for the same explicit identity."""
        get_report_v2 = getattr(self._v2_facade, "get_report_v2", None)
        if not callable(get_report_v2):
            raise AppQueryError("v2_facade must provide get_report_v2")
        v2 = get_report_v2(
            strategy_id=strategy_id,
            trade_date=trade_date,
            account_id=account_id,
        )
        if not isinstance(v2, DailyDecisionV2Report):
            raise AppQueryError("get_report_v2 returned an invalid report")
        resolved_strategy = _identity_string(v2, "strategy_id")
        if resolved_strategy is not None and resolved_strategy != strategy_id:
            raise AppQueryError("V2 strategy identity does not match V3 query")
        projection = self._projection_reader.get_latest(
            strategy_id=strategy_id,
            trade_date=_identity_string(v2, "signal_date") or trade_date,
            account_id=_identity_string(v2, "account_id") or account_id,
            sleeve_id=_identity_string(v2, "sleeve_id"),
        )
        return build_daily_decision_v3_report(v2, projection)


@dataclass(frozen=True)
class DailyDecisionV3Report:
    """V2-compatible cockpit plus typed R4 portfolio/risk sections."""

    v2: DailyDecisionV2Report
    readiness: Literal["ready", "blocked", "review"]
    blocking_reasons: tuple[str, ...]
    portfolio_construction: PortfolioConstructionSection
    tail_risk: TailRiskSection
    factor_risk: FactorRiskSection
    stress_tests: StressTestSection
    reconciliation: ReconciliationSection
    provenance: ProvenanceSection


def build_daily_decision_v3_report(
    v2: DailyDecisionV2Report,
    projection: DailyDecisionV3Projection | None,
) -> DailyDecisionV3Report:
    """Compose V3 without mutating or changing the existing V2 read model."""
    if projection is None:
        projection = _missing_projection()
        missing = ("R4_RISK_REPORT_MISSING",)
    else:
        missing = ()
    reasons: list[str] = list(missing)
    reasons.extend(projection.blocking_reasons)
    v2_status = str(v2.readiness.get("status", "blocked"))
    if v2_status == "blocked":
        reasons.append("V2_READINESS_BLOCKED")
    if not missing:
        if projection.portfolio_construction.status not in {"optimal", "legacy"}:
            reasons.append("PORTFOLIO_CONSTRUCTION_NOT_READY")
        if projection.reconciliation.status != "reconciled":
            reasons.append("RECONCILIATION_MISMATCH")
        reasons.extend(_projection_evidence_reasons(projection))
    stable_reasons = tuple(dict.fromkeys(reasons))
    readiness = (
        "blocked"
        if stable_reasons
        else ("review" if v2_status == "review" else "ready")
    )
    return DailyDecisionV3Report(
        v2=v2,
        readiness=readiness,
        blocking_reasons=stable_reasons,
        portfolio_construction=projection.portfolio_construction,
        tail_risk=projection.tail_risk,
        factor_risk=projection.factor_risk,
        stress_tests=projection.stress_tests,
        reconciliation=projection.reconciliation,
        provenance=projection.provenance,
    )


def _missing_projection() -> DailyDecisionV3Projection:
    return DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(status="unavailable"),
        tail_risk=TailRiskSection(None, None, None, None, None),
        factor_risk=FactorRiskSection("unavailable", None, {}, {}, None),
        stress_tests=StressTestSection("unavailable", {}),
        reconciliation=ReconciliationSection("unavailable", (), None),
        provenance=ProvenanceSection(None, None, None, (), None),
    )


def _identity_string(report: DailyDecisionV2Report, key: str) -> str | None:
    value = report.identity.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _projection_evidence_reasons(
    projection: DailyDecisionV3Projection,
) -> tuple[str, ...]:
    """Independently fail closed on incomplete persisted R4 evidence."""
    reasons: list[str] = []
    construction = projection.portfolio_construction
    if construction.status == "optimal" and (
        not construction.policy_digest
        or construction.solver not in {"OSQP", "CLARABEL"}
        or not construction.solver_version
        or construction.solver_status != "optimal"
        or construction.duration_ms is None
        or not math.isfinite(construction.duration_ms)
        or construction.duration_ms < 0.0
    ):
        reasons.append("PORTFOLIO_CONSTRUCTION_EVIDENCE_INVALID")

    tail_values = (
        projection.tail_risk.historical_es99,
        projection.tail_risk.historical_var99,
        projection.tail_risk.parametric_var99,
        projection.tail_risk.monte_carlo_var99,
    )
    if (
        any(value is None for value in tail_values)
        or any(
            not math.isfinite(value) or value < 0.0
            for value in tail_values
            if value is not None
        )
        or projection.tail_risk.monte_carlo_seed is None
    ):
        reasons.append("TAIL_RISK_INCOMPLETE")

    stress = projection.stress_tests
    if (
        not stress.catalog_version
        or stress.catalog_version == "unavailable"
        or not stress.losses
        or any(
            not name or not math.isfinite(loss) or loss < 0.0
            for name, loss in stress.losses.items()
        )
    ):
        reasons.append("STRESS_TESTS_INCOMPLETE")

    factor = projection.factor_risk
    if factor.availability not in {"available", "partial", "unavailable"} or (
        factor.availability != "unavailable"
        and (
            factor.total_risk is None
            or not math.isfinite(factor.total_risk)
            or factor.total_risk < 0.0
            or not factor.marginal_contributions
            or not factor.percentage_contributions
        )
    ):
        reasons.append("FACTOR_RISK_EVIDENCE_INVALID")

    reconciliation = projection.reconciliation
    if reconciliation.status == "reconciled" and reconciliation.differences:
        reasons.append("RECONCILIATION_EVIDENCE_INVALID")

    provenance = projection.provenance
    timestamps = (
        provenance.decision_time,
        provenance.knowledge_cutoff,
        provenance.publication_cutoff,
        provenance.generated_at,
    )
    if (
        any(value is None or not value.strip() for value in timestamps)
        or not provenance.source_snapshot_ids
        or any(not value.strip() for value in provenance.source_snapshot_ids)
        or len(set(provenance.source_snapshot_ids))
        != len(provenance.source_snapshot_ids)
    ):
        reasons.append("PROVENANCE_INCOMPLETE")
    return tuple(reasons)
