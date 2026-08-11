"""Public contract tests for constrained R4 portfolio optimization."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from ditto_portfolio.rebalancing._optimization_input import PreparedOptimizationInput
from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioConstructionPolicy,
    PortfolioOptimizationRequest,
)
from ditto_portfolio.rebalancing.optimizer import CVXPYPortfolioOptimizer


def _request(
    *,
    method: OptimizationMethod,
    covariance: np.ndarray,
    scenarios: np.ndarray | None = None,
    max_weight: float = 1.0,
    min_observations: int = 60,
) -> PortfolioOptimizationRequest:
    count = covariance.shape[0]
    return PortfolioOptimizationRequest(
        policy=PortfolioConstructionPolicy(
            policy_id="r4-test",
            version=1,
            method=method,
            turnover_penalty_bps=0.0,
            max_weight=max_weight,
            min_observations=min_observations,
        ),
        instrument_ids=tuple(range(1, count + 1)),
        covariance=covariance,
        scenario_returns=scenarios,
        candidate_weights=tuple(1.0 / count for _ in range(count)),
        current_weights=tuple(0.0 for _ in range(count)),
        source_snapshot_ids=("snap-1",),
    )


def test_mvo_matches_two_asset_minimum_variance_solution() -> None:
    result = CVXPYPortfolioOptimizer().optimize(
        _request(
            method=OptimizationMethod.MVO,
            covariance=np.diag([0.04, 0.01]),
        )
    )

    assert result.success is True
    assert result.solver == "OSQP"
    assert result.solver_status == "optimal"
    assert result.weights == pytest.approx((0.2, 0.8), abs=1e-5)
    assert result.constraint_violations == ()


def test_historical_cvar_respects_hard_max_weight() -> None:
    result = CVXPYPortfolioOptimizer().optimize(
        _request(
            method=OptimizationMethod.HISTORICAL_CVAR,
            covariance=np.diag([0.04, 0.01]),
            scenarios=np.array(
                [
                    [-0.10, -0.02],
                    [-0.08, -0.01],
                    [0.02, 0.00],
                    [0.01, 0.00],
                ]
            ),
            max_weight=0.8,
            min_observations=4,
        )
    )

    assert result.success is True
    assert result.solver == "CLARABEL"
    assert sum(result.weights) == pytest.approx(1.0, abs=1e-6)
    assert max(result.weights) <= 0.8 + 1e-6
    assert result.weights[1] == pytest.approx(0.8, abs=1e-5)


def test_risk_parity_reconciles_equal_risk_contributions() -> None:
    result = CVXPYPortfolioOptimizer().optimize(
        _request(
            method=OptimizationMethod.RISK_PARITY,
            covariance=np.diag([0.04, 0.01]),
        )
    )

    assert result.success is True
    assert result.solver == "CLARABEL"
    assert result.weights == pytest.approx((1 / 3, 2 / 3), abs=1e-4)
    assert result.risk_contribution_error is not None
    assert result.risk_contribution_error <= 1e-4


def test_risk_parity_reports_contributions_from_repaired_covariance() -> None:
    result = CVXPYPortfolioOptimizer().optimize(
        _request(
            method=OptimizationMethod.RISK_PARITY,
            covariance=np.zeros((2, 2)),
        )
    )

    assert result.success is True
    assert result.covariance_repaired is True
    assert result.risk_contributions == pytest.approx((0.5, 0.5))
    assert result.risk_contribution_error == pytest.approx(0.0)


def test_optimizer_fails_closed_when_candidate_capacity_is_exceeded() -> None:
    count = 501
    result = CVXPYPortfolioOptimizer().optimize(
        _request(
            method=OptimizationMethod.MVO,
            covariance=np.eye(count),
        )
    )

    assert result.success is False
    assert result.failure_code == "candidate_capacity_exceeded"
    assert result.weights == ()


def test_min_weight_uses_deterministic_active_set_and_allows_zero_weights() -> None:
    request = _request(
        method=OptimizationMethod.MVO,
        covariance=np.diag([0.01, 100.0, 0.02]),
    )
    request = PortfolioOptimizationRequest(
        policy=PortfolioConstructionPolicy(
            policy_id="r4-min-weight",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            min_weight=0.20,
        ),
        instrument_ids=request.instrument_ids,
        covariance=request.covariance,
        scenario_returns=None,
        candidate_weights=request.candidate_weights,
        current_weights=request.current_weights,
        source_snapshot_ids=request.source_snapshot_ids,
    )

    first = CVXPYPortfolioOptimizer().optimize(request)
    second = CVXPYPortfolioOptimizer().optimize(request)

    assert first.success is True
    assert first.weights == pytest.approx(second.weights)
    assert first.weights[1] == pytest.approx(0.0)
    assert all(weight == 0.0 or weight >= 0.20 - 1e-6 for weight in first.weights)


def test_optimal_inaccurate_is_saved_as_failure_not_published() -> None:
    class _InaccurateOptimizer(CVXPYPortfolioOptimizer):
        def _solve(
            self,
            request: PortfolioOptimizationRequest,
            prepared: PreparedOptimizationInput,
        ) -> tuple[np.ndarray | None, str, str, float | None]:
            return np.array([0.5, 0.5]), "OSQP", "optimal_inaccurate", 0.0

    result = _InaccurateOptimizer().optimize(
        _request(
            method=OptimizationMethod.MVO,
            covariance=np.eye(2),
        )
    )

    assert result.success is False
    assert result.failure_code == "solver_not_optimal"
    assert result.solver_status == "optimal_inaccurate"


def test_risk_parity_enforces_max_turnover_inside_convex_problem() -> None:
    base = _request(
        method=OptimizationMethod.RISK_PARITY,
        covariance=np.diag([0.04, 0.01]),
    )
    request = PortfolioOptimizationRequest(
        policy=PortfolioConstructionPolicy(
            policy_id="risk-parity-turnover",
            version=1,
            method=OptimizationMethod.RISK_PARITY,
            max_turnover=0.10,
            risk_contribution_tolerance=1.0,
        ),
        instrument_ids=base.instrument_ids,
        covariance=base.covariance,
        scenario_returns=None,
        candidate_weights=base.candidate_weights,
        current_weights=(1.0, 0.0),
        source_snapshot_ids=base.source_snapshot_ids,
    )

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is True
    assert (
        sum(
            abs(weight - current)
            for weight, current in zip(
                result.weights,
                request.current_weights,
                strict=True,
            )
        )
        <= 0.10 + 1e-6
    )


def test_policy_digest_covers_timeout_and_verification_tolerances() -> None:
    base = PortfolioConstructionPolicy(
        policy_id="digest",
        version=1,
        method=OptimizationMethod.MVO,
    )

    assert (
        base.digest
        != PortfolioConstructionPolicy(
            policy_id="digest",
            version=1,
            method=OptimizationMethod.MVO,
            solver_timeout_seconds=base.solver_timeout_seconds + 1.0,
        ).digest
    )
    assert (
        base.digest
        != PortfolioConstructionPolicy(
            policy_id="digest",
            version=1,
            method=OptimizationMethod.MVO,
            constraint_tolerance=base.constraint_tolerance * 10.0,
        ).digest
    )


@pytest.mark.parametrize(
    "field",
    [
        "turnover_penalty_bps",
        "max_turnover",
        "solver_timeout_seconds",
        "constraint_tolerance",
        "risk_contribution_tolerance",
    ],
)
def test_policy_rejects_non_finite_verification_and_solver_values(field: str) -> None:
    kwargs = {field: float("nan")}

    with pytest.raises(ValueError, match="finite"):
        PortfolioConstructionPolicy(
            policy_id="non-finite",
            version=1,
            method=OptimizationMethod.MVO,
            **kwargs,
        )


def test_optimizer_rejects_blank_or_duplicate_snapshot_evidence() -> None:
    base = _request(method=OptimizationMethod.MVO, covariance=np.eye(2))

    for snapshots in (("",), ("snap-1", "snap-1")):
        request = PortfolioOptimizationRequest(
            policy=base.policy,
            instrument_ids=base.instrument_ids,
            covariance=base.covariance,
            scenario_returns=base.scenario_returns,
            candidate_weights=base.candidate_weights,
            current_weights=base.current_weights,
            source_snapshot_ids=snapshots,
        )
        result = CVXPYPortfolioOptimizer().optimize(request)

        assert result.success is False
        assert result.failure_code == "missing_snapshot"


def test_optimizer_rejects_empty_eligibility_vector_for_nonempty_universe() -> None:
    request = _request(method=OptimizationMethod.MVO, covariance=np.eye(2))

    result = CVXPYPortfolioOptimizer().optimize(replace(request, eligible=()))

    assert result.success is False
    assert result.failure_code == "shape_mismatch"


def test_industry_caps_require_complete_industry_mapping() -> None:
    base = _request(method=OptimizationMethod.MVO, covariance=np.eye(2))
    request = PortfolioOptimizationRequest(
        policy=PortfolioConstructionPolicy(
            policy_id="industry-cap",
            version=1,
            method=OptimizationMethod.MVO,
            industry_caps=(("bank", 0.60),),
        ),
        instrument_ids=base.instrument_ids,
        covariance=base.covariance,
        scenario_returns=None,
        candidate_weights=base.candidate_weights,
        current_weights=base.current_weights,
        industries=("bank", None),
        source_snapshot_ids=base.source_snapshot_ids,
    )

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is False
    assert result.failure_code == "missing_industries"


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("candidate_weights", (float("nan"), 0.0)),
        ("current_weights", (float("inf"), 0.0)),
        ("current_weights", (-0.1, 0.0)),
    ],
)
def test_optimizer_rejects_invalid_candidate_and_current_weights(
    field: str,
    values: tuple[float, ...],
) -> None:
    base = _request(method=OptimizationMethod.MVO, covariance=np.eye(2))
    request = PortfolioOptimizationRequest(
        policy=base.policy,
        instrument_ids=base.instrument_ids,
        covariance=base.covariance,
        scenario_returns=base.scenario_returns,
        candidate_weights=(
            values if field == "candidate_weights" else base.candidate_weights
        ),
        current_weights=(
            values if field == "current_weights" else base.current_weights
        ),
        source_snapshot_ids=base.source_snapshot_ids,
    )

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is False
    assert result.failure_code == "invalid_weights"


def test_historical_cvar_requires_policy_minimum_scenarios() -> None:
    request = _request(
        method=OptimizationMethod.HISTORICAL_CVAR,
        covariance=np.eye(2),
        scenarios=np.asarray(((-0.1, 0.0), (0.0, -0.1))),
    )

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is False
    assert result.failure_code == "insufficient_scenarios"


def test_min_weight_active_set_is_nonempty_when_all_initial_weights_are_small() -> None:
    count = 5
    request = PortfolioOptimizationRequest(
        policy=PortfolioConstructionPolicy(
            policy_id="symmetric-min-weight",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            min_weight=0.30,
        ),
        instrument_ids=tuple(range(1, count + 1)),
        covariance=np.eye(count),
        scenario_returns=None,
        candidate_weights=tuple(1.0 / count for _ in range(count)),
        current_weights=tuple(0.0 for _ in range(count)),
        source_snapshot_ids=("snap-1",),
    )

    first = CVXPYPortfolioOptimizer().optimize(request)
    second = CVXPYPortfolioOptimizer().optimize(request)

    assert first.success is True
    assert first.weights == pytest.approx(second.weights)
    assert sum(weight > 1e-8 for weight in first.weights) == 3
    assert all(weight == 0.0 or weight >= 0.30 - 1e-6 for weight in first.weights)
