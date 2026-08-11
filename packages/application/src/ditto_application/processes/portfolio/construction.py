"""PIT-safe application orchestration for R4 portfolio construction."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import polars as pl
from ditto_features.risk_estimation.covariance import (
    ReturnMatrixRequest,
    ReturnRiskEstimate,
    RiskEstimationError,
    RiskEstimationEvidence,
    ShrinkageCovarianceEstimator,
)
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.rebalancing.optimization_models import (
    PortfolioConstructionPolicy,
    PortfolioOptimizationRequest,
    PortfolioOptimizationResult,
    PortfolioOptimizer,
)
from ditto_strategy.alpha.models import TargetPortfolio

__all__ = [
    "PortfolioConstructionData",
    "PortfolioConstructionDecision",
    "PortfolioConstructionIdentity",
    "PortfolioConstructionInputReader",
    "PortfolioConstructionProcess",
    "PortfolioConstructionQuery",
    "PortfolioConstructionTemporalContext",
    "PortfolioPolicyReader",
]


@dataclass(frozen=True)
class PortfolioConstructionIdentity:
    """Account, sleeve, strategy, and run identity for policy binding."""

    account_id: str
    sleeve_id: str
    strategy_id: str
    run_id: str
    trade_date: str


@dataclass(frozen=True)
class PortfolioConstructionTemporalContext:
    """Explicit visibility boundaries and source revision universe."""

    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioConstructionQuery:
    """Narrow input query owned by the application consumer."""

    identity: PortfolioConstructionIdentity
    temporal: PortfolioConstructionTemporalContext
    instrument_ids: tuple[InstrumentId, ...]
    lookback_sessions: int
    min_observations: int


@dataclass(frozen=True)
class PortfolioConstructionData:
    """PIT return observations plus current portfolio constraint inputs."""

    return_frame: pl.DataFrame
    current_weights: Mapping[InstrumentId, float]
    expected_returns: Mapping[InstrumentId, float] | None = None
    industries: Mapping[InstrumentId, str] | None = None
    eligibility: Mapping[InstrumentId, bool] | None = None


@dataclass(frozen=True)
class PortfolioConstructionDecision:
    """Constructed target or structured failure with audit evidence."""

    success: bool
    target: TargetPortfolio | None
    evidence: Mapping[str, object]
    failure_code: str | None = None
    failure_message: str | None = None


class PortfolioPolicyReader(Protocol):
    """Resolve one versioned policy binding for an account/sleeve/strategy."""

    def resolve(
        self,
        identity: PortfolioConstructionIdentity,
    ) -> PortfolioConstructionPolicy | None:
        """Return the active policy or ``None`` for unchanged legacy behavior."""
        ...


class PortfolioConstructionInputReader(Protocol):
    """Read PIT-visible construction inputs without exposing storage APIs."""

    def read(self, query: PortfolioConstructionQuery) -> PortfolioConstructionData:
        """Return the exact input revision requested by the process."""
        ...


class PortfolioConstructionProcess:
    """Coordinate policy resolution, risk estimation, and optimization."""

    def __init__(
        self,
        *,
        policy_reader: PortfolioPolicyReader,
        input_reader: PortfolioConstructionInputReader,
        optimizer: PortfolioOptimizer,
        covariance_estimator: ShrinkageCovarianceEstimator | None = None,
    ) -> None:
        """Store pure providers and consumer-owned reader ports."""
        self._policy_reader = policy_reader
        self._input_reader = input_reader
        self._optimizer = optimizer
        self._covariance_estimator = (
            covariance_estimator or ShrinkageCovarianceEstimator()
        )

    def construct(
        self,
        *,
        candidate: TargetPortfolio,
        identity: PortfolioConstructionIdentity,
        temporal: PortfolioConstructionTemporalContext,
    ) -> PortfolioConstructionDecision:
        """Construct an optimized target or preserve an unbound legacy target."""
        policy = self._policy_reader.resolve(identity)
        if policy is None:
            return PortfolioConstructionDecision(
                success=True,
                target=candidate,
                evidence={"mode": "legacy", "policy_digest": None},
            )
        candidate_ids = tuple(sorted(candidate.positions))
        query = PortfolioConstructionQuery(
            identity=identity,
            temporal=temporal,
            instrument_ids=candidate_ids,
            lookback_sessions=policy.lookback_sessions,
            min_observations=policy.min_observations,
        )
        prepared = self._prepare_data(
            candidate=candidate,
            candidate_ids=candidate_ids,
            query=query,
            policy=policy,
            temporal=temporal,
        )
        if isinstance(prepared, PortfolioConstructionDecision):
            return prepared
        data, instrument_ids = prepared
        estimate_or_failure = self._estimate(
            data=data,
            instrument_ids=instrument_ids,
            temporal=temporal,
            policy=policy,
        )
        if isinstance(estimate_or_failure, PortfolioConstructionDecision):
            return estimate_or_failure
        estimate = estimate_or_failure
        result = self._optimizer.optimize(
            PortfolioOptimizationRequest(
                policy=policy,
                instrument_ids=instrument_ids,
                covariance=estimate.covariance,
                scenario_returns=estimate.returns_matrix,
                candidate_weights=tuple(
                    float(candidate.positions.get(item, 0.0)) for item in instrument_ids
                ),
                current_weights=tuple(
                    float(data.current_weights.get(item, 0.0))
                    for item in instrument_ids
                ),
                source_snapshot_ids=temporal.source_snapshot_ids,
                expected_returns=(
                    tuple(float(data.expected_returns[item]) for item in instrument_ids)
                    if data.expected_returns is not None
                    else None
                ),
                industries=(
                    tuple(data.industries.get(item) for item in instrument_ids)
                    if data.industries is not None
                    else None
                ),
                eligible=(
                    tuple(data.eligibility.get(item, False) for item in instrument_ids)
                    if data.eligibility is not None
                    else None
                ),
            )
        )
        evidence = _optimization_evidence(result, estimate)
        return self._decision_from_result(
            candidate=candidate,
            instrument_ids=instrument_ids,
            policy=policy,
            result=result,
            evidence=evidence,
        )

    def _prepare_data(
        self,
        *,
        candidate: TargetPortfolio,
        candidate_ids: tuple[InstrumentId, ...],
        query: PortfolioConstructionQuery,
        policy: PortfolioConstructionPolicy,
        temporal: PortfolioConstructionTemporalContext,
    ) -> (
        tuple[PortfolioConstructionData, tuple[InstrumentId, ...]]
        | PortfolioConstructionDecision
    ):
        """Load a stable PIT input universe and validate all scalar evidence."""
        data_or_failure = self._read_input(query, policy, temporal)
        if isinstance(data_or_failure, PortfolioConstructionDecision):
            return data_or_failure
        data = data_or_failure
        current_failure = _validate_current_weights(data.current_weights, policy)
        if current_failure is not None:
            return current_failure
        instrument_ids = _construction_universe(candidate_ids, data.current_weights)
        if not instrument_ids:
            return PortfolioConstructionDecision(
                success=True,
                target=candidate,
                evidence={
                    "mode": "optimized_no_positions",
                    "policy_digest": policy.digest,
                    "source_snapshot_ids": temporal.source_snapshot_ids,
                },
            )
        if instrument_ids != candidate_ids:
            refreshed_or_failure = self._refresh_expanded_data(
                query,
                instrument_ids,
                data,
                policy,
                temporal,
            )
            if isinstance(refreshed_or_failure, PortfolioConstructionDecision):
                return refreshed_or_failure
            data = refreshed_or_failure
        expected_failure = _validate_expected_returns(
            data.expected_returns,
            instrument_ids,
            policy,
            temporal,
        )
        if expected_failure is not None:
            return expected_failure
        return data, instrument_ids

    def _refresh_expanded_data(
        self,
        query: PortfolioConstructionQuery,
        instrument_ids: tuple[InstrumentId, ...],
        initial: PortfolioConstructionData,
        policy: PortfolioConstructionPolicy,
        temporal: PortfolioConstructionTemporalContext,
    ) -> PortfolioConstructionData | PortfolioConstructionDecision:
        expanded_query = PortfolioConstructionQuery(
            identity=query.identity,
            temporal=query.temporal,
            instrument_ids=instrument_ids,
            lookback_sessions=query.lookback_sessions,
            min_observations=query.min_observations,
        )
        refreshed = self._read_input(expanded_query, policy, temporal)
        if isinstance(refreshed, PortfolioConstructionDecision):
            return refreshed
        if refreshed.current_weights != initial.current_weights:
            return _input_failure(policy, temporal, "current holdings changed")
        return refreshed

    def _read_input(
        self,
        query: PortfolioConstructionQuery,
        policy: PortfolioConstructionPolicy,
        temporal: PortfolioConstructionTemporalContext,
    ) -> PortfolioConstructionData | PortfolioConstructionDecision:
        """Translate input-provider failures into auditable fail-closed evidence."""
        try:
            data = self._input_reader.read(query)
        except Exception as exc:
            return _input_failure(
                policy,
                temporal,
                f"PIT portfolio input unavailable: {type(exc).__name__}: {exc}",
                code="risk_input_unavailable",
            )
        return data

    @staticmethod
    def _decision_from_result(
        *,
        candidate: TargetPortfolio,
        instrument_ids: tuple[InstrumentId, ...],
        policy: PortfolioConstructionPolicy,
        result: PortfolioOptimizationResult,
        evidence: Mapping[str, object],
    ) -> PortfolioConstructionDecision:
        """Apply shadow/enforced publication semantics to one solver result."""
        if not result.success:
            return PortfolioConstructionDecision(
                success=False,
                target=None,
                evidence={**evidence, "mode": policy.execution_mode},
                failure_code=result.failure_code or "optimization_failed",
                failure_message=result.failure_message,
            )
        optimized_target = TargetPortfolio(
            trade_date=candidate.trade_date,
            strategy_id=candidate.strategy_id,
            run_id=candidate.run_id,
            positions=dict(zip(instrument_ids, result.weights, strict=True)),
            cash_target=policy.cash_target,
        )
        if policy.execution_mode == "shadow":
            return PortfolioConstructionDecision(
                success=True,
                target=candidate,
                evidence={
                    **evidence,
                    "mode": "shadow",
                    "shadow_positions": optimized_target.positions,
                },
            )
        return PortfolioConstructionDecision(
            success=True,
            target=optimized_target,
            evidence={**evidence, "mode": "enforced"},
        )

    def _estimate(
        self,
        *,
        data: PortfolioConstructionData,
        instrument_ids: tuple[InstrumentId, ...],
        temporal: PortfolioConstructionTemporalContext,
        policy: PortfolioConstructionPolicy,
    ) -> ReturnRiskEstimate | PortfolioConstructionDecision:
        try:
            return self._covariance_estimator.estimate(
                ReturnMatrixRequest(
                    frame=data.return_frame,
                    instrument_ids=instrument_ids,
                    evidence=RiskEstimationEvidence(
                        decision_time=temporal.decision_time,
                        knowledge_cutoff=temporal.knowledge_cutoff,
                        publication_cutoff=temporal.publication_cutoff,
                        source_snapshot_ids=temporal.source_snapshot_ids,
                    ),
                    lookback_sessions=policy.lookback_sessions,
                    min_observations=policy.min_observations,
                )
            )
        except RiskEstimationError as exc:
            return PortfolioConstructionDecision(
                success=False,
                target=None,
                evidence={
                    "policy_digest": policy.digest,
                    "source_snapshot_ids": temporal.source_snapshot_ids,
                },
                failure_code="risk_input_invalid",
                failure_message=str(exc),
            )


def _optimization_evidence(
    result: PortfolioOptimizationResult,
    estimate: ReturnRiskEstimate,
) -> dict[str, object]:
    return {
        "policy_digest": result.policy_digest,
        "source_snapshot_ids": result.source_snapshot_ids,
        "solver": result.solver,
        "solver_version": result.solver_version,
        "solver_status": result.solver_status,
        "observation_count": estimate.observation_count,
        "shrinkage": estimate.shrinkage,
        "covariance_repaired": (
            estimate.covariance_repaired or result.covariance_repaired
        ),
        "constraint_violations": result.constraint_violations,
        "failure_code": result.failure_code,
    }


def _construction_universe(
    candidate_ids: tuple[InstrumentId, ...],
    current_weights: Mapping[InstrumentId, float],
) -> tuple[InstrumentId, ...]:
    current_ids = {
        instrument_id
        for instrument_id, weight in current_weights.items()
        if float(weight) != 0.0
    }
    return tuple(sorted(set(candidate_ids) | current_ids))


def _validate_current_weights(
    current_weights: Mapping[InstrumentId, float],
    policy: PortfolioConstructionPolicy,
) -> PortfolioConstructionDecision | None:
    if all(
        math.isfinite(float(weight)) and float(weight) >= 0.0
        for weight in current_weights.values()
    ):
        return None
    return PortfolioConstructionDecision(
        success=False,
        target=None,
        evidence={"policy_digest": policy.digest},
        failure_code="risk_input_invalid",
        failure_message="current weights must be finite and non-negative",
    )


def _validate_expected_returns(
    expected_returns: Mapping[InstrumentId, float] | None,
    instrument_ids: tuple[InstrumentId, ...],
    policy: PortfolioConstructionPolicy,
    temporal: PortfolioConstructionTemporalContext,
) -> PortfolioConstructionDecision | None:
    if expected_returns is None or all(
        instrument_id in expected_returns
        and math.isfinite(float(expected_returns[instrument_id]))
        for instrument_id in instrument_ids
    ):
        return None
    return _input_failure(policy, temporal, "expected returns are incomplete")


def _input_failure(
    policy: PortfolioConstructionPolicy,
    temporal: PortfolioConstructionTemporalContext,
    message: str,
    *,
    code: str = "risk_input_invalid",
) -> PortfolioConstructionDecision:
    return PortfolioConstructionDecision(
        success=False,
        target=None,
        evidence={
            "policy_digest": policy.digest,
            "source_snapshot_ids": temporal.source_snapshot_ids,
        },
        failure_code=code,
        failure_message=message,
    )
