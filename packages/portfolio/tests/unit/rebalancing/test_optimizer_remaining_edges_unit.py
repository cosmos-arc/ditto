"""Boundary and fail-closed coverage for the CVXPY portfolio optimizer."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from cvxpy.constraints.constraint import Constraint
from cvxpy.error import SolverError
from cvxpy.expressions.variable import Variable
from cvxpy.problems.problem import Problem
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.rebalancing import optimizer as optimizer_module
from ditto_portfolio.rebalancing._optimization_input import (
    PreparedOptimizationInput,
    prepare_input,
)
from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioConstructionPolicy,
    PortfolioOptimizationRequest,
)
from ditto_portfolio.rebalancing.optimizer import CVXPYPortfolioOptimizer


def _request(
    *,
    covariance: np.ndarray,
    policy: PortfolioConstructionPolicy,
) -> PortfolioOptimizationRequest:
    count = covariance.shape[0]
    return PortfolioOptimizationRequest(
        policy=policy,
        instrument_ids=tuple(InstrumentId(index) for index in range(1, count + 1)),
        covariance=covariance,
        scenario_returns=None,
        candidate_weights=tuple(1.0 / count for _ in range(count)),
        current_weights=tuple(0.0 for _ in range(count)),
        source_snapshot_ids=("snapshot-1",),
    )


class _FixedSolveOptimizer(CVXPYPortfolioOptimizer):
    def __init__(
        self,
        values: np.ndarray | None,
        *,
        status: str = "optimal",
    ) -> None:
        self._values = values
        self._status = status

    def _solve(
        self,
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
    ) -> tuple[np.ndarray | None, str, str, float | None]:
        del request, prepared
        return self._values, "OSQP", self._status, 0.0


class _RaisingOptimizer(CVXPYPortfolioOptimizer):
    def __init__(self, error: Exception) -> None:
        self._error = error

    def _solve(
        self,
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
    ) -> tuple[np.ndarray | None, str, str, float | None]:
        del request, prepared
        raise self._error


def test_min_weight_resolves_full_active_set_when_a_feasible_solution_exists() -> None:
    request = _request(
        covariance=np.diag([1 / 3, 1 / 3, 1 / 3, 1.0]),
        policy=PortfolioConstructionPolicy(
            policy_id="full-active-set",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            min_weight=0.20,
            max_weight=0.30,
        ),
    )

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is True
    assert result.constraint_violations == ()
    tolerance = request.policy.constraint_tolerance
    assert all(
        0.20 - tolerance <= weight <= 0.30 + tolerance for weight in result.weights
    )


def test_min_weight_keeps_full_active_solution_that_already_meets_the_floor() -> None:
    base = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="full-active-set-already-valid",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            min_weight=0.20,
        ),
    )
    request = replace(base, expected_returns=(0.20, 0.0))

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is True
    assert result.weights[0] > result.weights[1]
    assert min(result.weights) >= 0.20 - request.policy.constraint_tolerance


def test_min_weight_full_active_set_remains_fail_closed_when_infeasible() -> None:
    class _SecondPassInfeasibleOptimizer(CVXPYPortfolioOptimizer):
        def __init__(self) -> None:
            self.minimums: list[float] = []

        def _solve_fixed_universe(
            self,
            request: PortfolioOptimizationRequest,
            prepared: PreparedOptimizationInput,
            *,
            minimum_weight: float,
        ) -> tuple[np.ndarray | None, str, str, float | None]:
            del request, prepared
            self.minimums.append(minimum_weight)
            if minimum_weight == 0.0:
                return np.asarray([0.3, 0.3, 0.3, 0.1]), "OSQP", "optimal", 1.0
            return None, "OSQP", "infeasible", None

    request = _request(
        covariance=np.diag([1 / 3, 1 / 3, 1 / 3, 1.0]),
        policy=PortfolioConstructionPolicy(
            policy_id="infeasible-full-active-set",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            min_weight=0.20,
            max_weight=0.30,
        ),
    )
    optimizer = _SecondPassInfeasibleOptimizer()

    result = optimizer.optimize(request)

    assert optimizer.minimums == [0.0, 0.20]
    assert result.success is False
    assert result.failure_code == "solver_not_optimal"
    assert result.solver_status == "infeasible"
    assert result.weights == ()


@pytest.mark.parametrize(
    "error",
    [
        SolverError("solver failed"),
        ValueError("invalid solver value"),
        ArithmeticError(),
    ],
)
def test_solver_boundary_errors_are_structured_failures(error: Exception) -> None:
    request = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="solver-error",
            version=1,
            method=OptimizationMethod.MVO,
        ),
    )

    result = _RaisingOptimizer(error).optimize(request)

    assert result.success is False
    assert result.failure_code == "solver_error"
    assert result.failure_message == str(error)
    assert result.weights == ()


def test_solver_output_violating_constraints_is_never_published() -> None:
    request = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="invalid-solver-output",
            version=1,
            method=OptimizationMethod.MVO,
        ),
    )

    result = _FixedSolveOptimizer(np.asarray([0.4, 0.4])).optimize(request)

    assert result.success is False
    assert result.failure_code == "constraint_violation"
    assert result.constraint_violations == ("total_weight",)


def test_unreconciled_risk_budget_is_never_published() -> None:
    request = _request(
        covariance=np.diag([0.04, 0.01]),
        policy=PortfolioConstructionPolicy(
            policy_id="unreconciled-risk-budget",
            version=1,
            method=OptimizationMethod.RISK_PARITY,
        ),
    )

    result = _FixedSolveOptimizer(np.asarray([0.5, 0.5])).optimize(request)

    assert result.success is False
    assert result.failure_code == "risk_budget_not_reconciled"
    assert result.failure_message == "risk contribution error 0.3"


def test_initial_nonoptimal_min_weight_solve_is_preserved_as_failure() -> None:
    class _InitialFailureOptimizer(CVXPYPortfolioOptimizer):
        def _solve_fixed_universe(
            self,
            request: PortfolioOptimizationRequest,
            prepared: PreparedOptimizationInput,
            *,
            minimum_weight: float,
        ) -> tuple[np.ndarray | None, str, str, float | None]:
            del request, prepared, minimum_weight
            return None, "OSQP", "infeasible", None

    request = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="initial-infeasible",
            version=1,
            method=OptimizationMethod.MVO,
            min_weight=0.20,
        ),
    )

    result = _InitialFailureOptimizer().optimize(request)

    assert result.success is False
    assert result.failure_code == "solver_not_optimal"
    assert result.solver_status == "infeasible"


@pytest.mark.parametrize(
    ("count", "cash_target"),
    [(1, 0.5), (2, 0.0)],
)
def test_infeasible_min_weight_cardinality_fails_deterministically(
    count: int,
    cash_target: float,
) -> None:
    request = _request(
        covariance=np.eye(count),
        policy=PortfolioConstructionPolicy(
            policy_id="infeasible-cardinality",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            cash_target=cash_target,
            min_weight=0.60,
            max_weight=0.60,
        ),
    )

    first = CVXPYPortfolioOptimizer().optimize(request)
    second = CVXPYPortfolioOptimizer().optimize(request)

    assert first == second
    assert first.success is False
    assert first.failure_code == "solver_not_optimal"
    assert first.solver_status == "active_set_empty"


def test_min_weight_tolerance_trims_ties_by_instrument_id() -> None:
    request = _request(
        covariance=np.eye(6),
        policy=PortfolioConstructionPolicy(
            policy_id="tolerance-tie-break",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            min_weight=0.20,
            constraint_tolerance=0.10,
        ),
    )
    prepared = prepare_input(request)

    first = optimizer_module._deterministic_active_set(
        request,
        prepared,
        np.full(6, 1 / 6),
    )
    second = optimizer_module._deterministic_active_set(
        request,
        prepared,
        np.full(6, 1 / 6),
    )

    assert first == second == (0, 1, 2, 3, 4)


def test_risk_parity_min_weight_and_industry_cap_apply_to_reduced_universe() -> None:
    base = _request(
        covariance=np.diag([1.0, 1.0, 100.0]),
        policy=PortfolioConstructionPolicy(
            policy_id="risk-parity-active-set",
            version=1,
            method=OptimizationMethod.RISK_PARITY,
            min_weight=0.20,
            industry_caps=(("financial", 0.80),),
        ),
    )
    request = replace(base, industries=("financial", "industrial", "technology"))

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is True
    assert result.weights == pytest.approx((0.5, 0.5, 0.0), abs=1e-4)
    assert result.risk_contribution_error is not None
    assert result.risk_contribution_error <= request.policy.risk_contribution_tolerance


def test_infeasible_risk_parity_turnover_has_no_publishable_weights() -> None:
    base = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="risk-parity-zero-turnover",
            version=1,
            method=OptimizationMethod.RISK_PARITY,
            max_turnover=0.0,
        ),
    )
    request = replace(base, current_weights=(0.0, 0.0))

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is False
    assert result.failure_code == "solver_error"
    assert result.failure_message
    assert result.weights == ()


def test_risk_parity_without_primal_solver_values_fails_closed() -> None:
    class _NoResultOptimizer(CVXPYPortfolioOptimizer):
        @staticmethod
        def _run_solver(
            problem: Problem,
            solver: str,
            timeout_seconds: float,
        ) -> None:
            del problem, solver, timeout_seconds

    request = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="risk-parity-no-primal-values",
            version=1,
            method=OptimizationMethod.RISK_PARITY,
        ),
    )

    result = _NoResultOptimizer().optimize(request)

    assert result.success is False
    assert result.failure_code == "solver_not_optimal"
    assert result.solver_status == "None"
    assert result.weights == ()


def test_standard_optimizer_enforces_zero_turnover_constraint() -> None:
    base = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="mvo-zero-turnover",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            max_turnover=0.0,
        ),
    )
    request = replace(base, current_weights=(0.5, 0.5))

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is True
    assert result.weights == pytest.approx((0.5, 0.5), abs=1e-6)


def test_standard_optimizer_enforces_industry_cap() -> None:
    base = _request(
        covariance=np.diag([0.01, 0.04]),
        policy=PortfolioConstructionPolicy(
            policy_id="mvo-industry-cap",
            version=1,
            method=OptimizationMethod.MVO,
            turnover_penalty_bps=0.0,
            industry_caps=(("bank", 0.40),),
        ),
    )
    request = replace(base, industries=("bank", "technology"))

    result = CVXPYPortfolioOptimizer().optimize(request)

    assert result.success is True
    assert result.weights == pytest.approx((0.4, 0.6), abs=1e-6)


def test_constraint_audit_reports_each_hard_limit() -> None:
    default_request = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="constraint-audit-default",
            version=1,
            method=OptimizationMethod.MVO,
        ),
    )
    min_weight_request = replace(
        default_request,
        policy=replace(default_request.policy, min_weight=0.20),
    )
    turnover_request = replace(
        default_request,
        policy=replace(default_request.policy, max_turnover=0.10),
        current_weights=(0.5, 0.5),
    )
    industry_request = replace(
        default_request,
        policy=replace(
            default_request.policy,
            industry_caps=(("bank", 0.40),),
        ),
        industries=("bank", "technology"),
    )

    audit = CVXPYPortfolioOptimizer._constraint_violations
    assert audit(default_request, np.asarray([0.4, 0.4])) == ("total_weight",)
    assert audit(default_request, np.asarray([-0.1, 1.1])) == (
        "long_only",
        "max_weight",
    )
    assert audit(min_weight_request, np.asarray([0.1, 0.9])) == ("min_weight",)
    assert audit(turnover_request, np.asarray([0.6, 0.4])) == ("max_turnover",)
    assert audit(industry_request, np.asarray([0.5, 0.5])) == ("industry_cap:bank",)


def test_degenerate_risk_evidence_and_absent_contributions_stay_unavailable() -> None:
    risk_contributions = CVXPYPortfolioOptimizer._risk_contributions

    assert risk_contributions(
        np.zeros(2),
        np.eye(2),
        OptimizationMethod.MVO,
    ) == (None, None)
    assert risk_contributions(
        np.asarray([0.5, 0.5]),
        np.zeros((2, 2)),
        OptimizationMethod.MVO,
    ) == (None, None)
    assert optimizer_module._expand_contributions(None, (0,), 2) is None


def test_solver_builders_reject_inconsistent_prepared_contracts() -> None:
    mvo_request = _request(
        covariance=np.eye(2),
        policy=PortfolioConstructionPolicy(
            policy_id="prepared-contract",
            version=1,
            method=OptimizationMethod.MVO,
        ),
    )
    prepared = prepare_input(mvo_request)
    cvar_request = replace(
        mvo_request,
        policy=replace(
            mvo_request.policy,
            method=OptimizationMethod.HISTORICAL_CVAR,
        ),
    )
    capped_request = replace(
        mvo_request,
        policy=replace(
            mvo_request.policy,
            industry_caps=(("bank", 0.50),),
        ),
        industries=("bank", "technology"),
    )

    with pytest.raises(ValueError, match="scenario_returns"):
        CVXPYPortfolioOptimizer._standard_objective(
            cvar_request,
            prepared,
            Variable(2),
            [],
        )
    constraints: list[Constraint] = []
    with pytest.raises(ValueError, match="require industries"):
        CVXPYPortfolioOptimizer._industry_constraints(
            capped_request,
            prepared,
            Variable(2),
            constraints,
            total_scale=None,
        )


def test_solver_scalar_boundary_preserves_none_and_rejects_invalid_values() -> None:
    assert optimizer_module._solver_float(None) is None

    for value in (True, "1.0", object()):
        with pytest.raises(ArithmeticError, match="real scalar"):
            optimizer_module._solver_float(value)
    for value in (float("nan"), float("inf"), np.float64("-inf")):
        with pytest.raises(ArithmeticError, match="finite"):
            optimizer_module._solver_float(value)
