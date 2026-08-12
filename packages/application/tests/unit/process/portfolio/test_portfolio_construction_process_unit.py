"""Application portfolio construction orchestration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_application.processes.portfolio.construction import (
    PortfolioConstructionData,
    PortfolioConstructionIdentity,
    PortfolioConstructionProcess,
    PortfolioConstructionQuery,
    PortfolioConstructionTemporalContext,
)
from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioConstructionPolicy,
    PortfolioOptimizationRequest,
    PortfolioOptimizationResult,
)
from ditto_portfolio.rebalancing.optimizer import CVXPYPortfolioOptimizer
from ditto_strategy.alpha.models import TargetPortfolio


class _PolicyReader:
    def __init__(self, policy: PortfolioConstructionPolicy | None) -> None:
        self.policy = policy

    def resolve(
        self,
        identity: PortfolioConstructionIdentity,
    ) -> PortfolioConstructionPolicy | None:
        return self.policy


class _InputReader:
    def __init__(self, data: PortfolioConstructionData) -> None:
        self.data = data
        self.calls = 0

    def read(self, query: PortfolioConstructionQuery) -> PortfolioConstructionData:
        self.calls += 1
        return self.data


def _frame(observations: int = 60) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for offset in range(observations):
        observed = start + timedelta(days=offset)
        for instrument_id, scale in ((1, 0.02), (2, 0.01)):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "observation_time": observed,
                    "knowledge_time": observed + timedelta(hours=1),
                    "publication_time": observed + timedelta(minutes=30),
                    "source_snapshot_id": "snap-1",
                    "return": scale * (((offset % 7) - 3) / 3),
                }
            )
    return pl.DataFrame(rows)


def _identity() -> PortfolioConstructionIdentity:
    return PortfolioConstructionIdentity(
        account_id="paper-1",
        sleeve_id="core",
        strategy_id="stock-selection",
        run_id="run-1",
        trade_date="2026-04-01",
    )


def _temporal() -> PortfolioConstructionTemporalContext:
    cutoff = datetime(2026, 3, 31, 23, tzinfo=UTC)
    return PortfolioConstructionTemporalContext(
        decision_time=datetime(2026, 4, 1, tzinfo=UTC),
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshot_ids=("snap-1",),
    )


def _policy() -> PortfolioConstructionPolicy:
    return PortfolioConstructionPolicy(
        policy_id="stock-mvo",
        version=1,
        method=OptimizationMethod.MVO,
        turnover_penalty_bps=0.0,
    )


def _candidate() -> TargetPortfolio:
    return TargetPortfolio(
        trade_date="2026-04-01",
        strategy_id="stock-selection",
        run_id="run-1",
        positions={1: 0.5, 2: 0.5},
    )


def test_bound_policy_builds_optimized_target_and_evidence() -> None:
    input_reader = _InputReader(
        PortfolioConstructionData(
            return_frame=_frame(),
            current_weights={1: 0.0, 2: 0.0},
            industries={1: "bank", 2: "tech"},
            eligibility={1: True, 2: True},
        )
    )
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(_policy()),
        input_reader=input_reader,
        optimizer=CVXPYPortfolioOptimizer(),
    )

    decision = process.construct(
        candidate=_candidate(),
        identity=_identity(),
        temporal=_temporal(),
    )

    assert decision.success is True
    assert decision.target is not None
    assert sum(decision.target.positions.values()) == pytest.approx(1.0)
    assert decision.target.positions[2] > decision.target.positions[1]
    assert decision.evidence["solver"] == "OSQP"
    assert decision.evidence["source_snapshot_ids"] == ("snap-1",)
    assert "shrinkage" in decision.evidence
    assert "covariance_repaired" in decision.evidence
    assert input_reader.calls == 1


def test_unbound_policy_preserves_legacy_target_without_reading_history() -> None:
    input_reader = _InputReader(
        PortfolioConstructionData(
            return_frame=pl.DataFrame(),
            current_weights={},
        )
    )
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(None),
        input_reader=input_reader,
        optimizer=CVXPYPortfolioOptimizer(),
    )
    candidate = _candidate()

    decision = process.construct(
        candidate=candidate,
        identity=_identity(),
        temporal=_temporal(),
    )

    assert decision.success is True
    assert decision.target is candidate
    assert decision.evidence == {"mode": "legacy", "policy_digest": None}
    assert input_reader.calls == 0


def test_insufficient_history_returns_structured_failure_without_fallback() -> None:
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(_policy()),
        input_reader=_InputReader(
            PortfolioConstructionData(
                return_frame=_frame(observations=59),
                current_weights={1: 0.0, 2: 0.0},
            )
        ),
        optimizer=CVXPYPortfolioOptimizer(),
    )

    decision = process.construct(
        candidate=_candidate(),
        identity=_identity(),
        temporal=_temporal(),
    )

    assert decision.success is False
    assert decision.target is None
    assert decision.failure_code == "risk_input_invalid"
    assert decision.evidence["policy_digest"] == _policy().digest
    assert "60" in str(decision.failure_message)


def test_process_output_is_independent_of_candidate_mapping_order() -> None:
    data = PortfolioConstructionData(
        return_frame=_frame(),
        current_weights={1: 0.0, 2: 0.0},
    )
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(_policy()),
        input_reader=_InputReader(data),
        optimizer=CVXPYPortfolioOptimizer(),
    )
    reversed_candidate = TargetPortfolio(
        trade_date="2026-04-01",
        strategy_id="stock-selection",
        run_id="run-1",
        positions={2: 0.5, 1: 0.5},
    )

    first = process.construct(
        candidate=_candidate(),
        identity=_identity(),
        temporal=_temporal(),
    )
    second = process.construct(
        candidate=reversed_candidate,
        identity=_identity(),
        temporal=_temporal(),
    )

    assert first.target is not None
    assert second.target is not None
    np.testing.assert_allclose(
        tuple(first.target.positions.values()),
        tuple(second.target.positions.values()),
    )


def test_shadow_policy_records_optimizer_result_without_changing_candidate() -> None:
    policy = PortfolioConstructionPolicy(
        policy_id="stock-mvo-shadow",
        version=1,
        method=OptimizationMethod.MVO,
        execution_mode="shadow",
        turnover_penalty_bps=0.0,
    )
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(policy),
        input_reader=_InputReader(
            PortfolioConstructionData(
                return_frame=_frame(),
                current_weights={1: 0.0, 2: 0.0},
            )
        ),
        optimizer=CVXPYPortfolioOptimizer(),
    )
    candidate = _candidate()

    decision = process.construct(
        candidate=candidate,
        identity=_identity(),
        temporal=_temporal(),
    )

    assert decision.success is True
    assert decision.target is candidate
    assert decision.evidence["mode"] == "shadow"
    assert decision.evidence["shadow_positions"] != candidate.positions


def test_shadow_policy_still_fails_closed_when_optimizer_fails() -> None:
    class _FailingOptimizer:
        def optimize(
            self,
            request: PortfolioOptimizationRequest,
        ) -> PortfolioOptimizationResult:
            return PortfolioOptimizationResult(
                success=False,
                weights=(),
                solver="OSQP",
                solver_version="1.1.3",
                solver_status="infeasible",
                policy_digest=request.policy.digest,
                source_snapshot_ids=request.source_snapshot_ids,
                failure_code="solver_not_optimal",
                failure_message="infeasible",
            )

    policy = PortfolioConstructionPolicy(
        policy_id="stock-mvo-shadow",
        version=1,
        method=OptimizationMethod.MVO,
        execution_mode="shadow",
    )
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(policy),
        input_reader=_InputReader(
            PortfolioConstructionData(
                return_frame=_frame(),
                current_weights={1: 0.5, 2: 0.5},
            )
        ),
        optimizer=_FailingOptimizer(),
    )

    decision = process.construct(
        candidate=_candidate(),
        identity=_identity(),
        temporal=_temporal(),
    )

    assert decision.success is False
    assert decision.target is None
    assert decision.failure_code == "solver_not_optimal"


def test_current_holding_outside_candidate_is_included_in_turnover_universe() -> None:
    class _CapturingOptimizer:
        request: PortfolioOptimizationRequest | None = None

        def optimize(
            self,
            request: PortfolioOptimizationRequest,
        ) -> PortfolioOptimizationResult:
            self.request = request
            return PortfolioOptimizationResult(
                success=False,
                weights=(),
                solver="OSQP",
                solver_version="1.1.3",
                solver_status="infeasible",
                policy_digest=request.policy.digest,
                source_snapshot_ids=request.source_snapshot_ids,
                failure_code="captured",
            )

    third = (
        _frame()
        .filter(pl.col("instrument_id") == 2)
        .with_columns(pl.lit(3, dtype=pl.Int64).alias("instrument_id"))
    )
    input_reader = _InputReader(
        PortfolioConstructionData(
            return_frame=pl.concat((_frame(), third)),
            current_weights={1: 0.5, 3: 0.5},
        )
    )
    optimizer = _CapturingOptimizer()
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(_policy()),
        input_reader=input_reader,
        optimizer=optimizer,
    )

    process.construct(
        candidate=_candidate(),
        identity=_identity(),
        temporal=_temporal(),
    )

    assert optimizer.request is not None
    assert optimizer.request.instrument_ids == (1, 2, 3)
    assert optimizer.request.candidate_weights == (0.5, 0.5, 0.0)
    assert optimizer.request.current_weights == (0.5, 0.0, 0.5)
    assert input_reader.calls == 2


def test_explicit_expected_returns_are_forwarded_without_using_candidate_scores() -> (
    None
):
    data = PortfolioConstructionData(
        return_frame=_frame(),
        current_weights={1: 0.5, 2: 0.5},
        expected_returns={1: 0.0, 2: 1.0},
    )
    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(_policy()),
        input_reader=_InputReader(data),
        optimizer=CVXPYPortfolioOptimizer(),
    )

    decision = process.construct(
        candidate=_candidate(),
        identity=_identity(),
        temporal=_temporal(),
    )

    assert decision.success is True
    assert decision.target is not None
    assert decision.target.positions[2] > 0.99


def test_input_reader_failure_returns_structured_failure_without_fallback() -> None:
    class _UnavailableInputReader:
        def read(self, query: PortfolioConstructionQuery) -> PortfolioConstructionData:
            del query
            raise OSError("PIT snapshot unavailable")

    process = PortfolioConstructionProcess(
        policy_reader=_PolicyReader(_policy()),
        input_reader=_UnavailableInputReader(),
        optimizer=CVXPYPortfolioOptimizer(),
    )

    decision = process.construct(
        candidate=_candidate(),
        identity=_identity(),
        temporal=_temporal(),
    )

    assert decision.success is False
    assert decision.target is None
    assert decision.failure_code == "risk_input_unavailable"
    assert decision.evidence["policy_digest"] == _policy().digest
    assert decision.evidence["source_snapshot_ids"] == ("snap-1",)
