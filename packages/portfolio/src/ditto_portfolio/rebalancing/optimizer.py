"""CVXPY provider for R4 constrained portfolio construction."""

from __future__ import annotations

import math
from importlib.metadata import version
from typing import Any, cast

import cvxpy as cp
import numpy as np
from cvxpy.constraints.constraint import Constraint
from cvxpy.expressions.expression import Expression
from cvxpy.expressions.variable import Variable
from cvxpy.problems.problem import Problem

from ditto_portfolio.rebalancing._optimization_input import (
    OptimizationInputError,
    PreparedOptimizationInput,
    prepare_input,
    subset_prepared_input,
)
from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioOptimizationRequest,
    PortfolioOptimizationResult,
)

__all__ = ["CVXPYPortfolioOptimizer"]

_MINIMUM_SCENARIOS = 2
_ACTIVE_WEIGHT_TOLERANCE = 1e-8
_cp = cast(Any, cp)


class CVXPYPortfolioOptimizer:
    """Fail-closed CVXPY provider with a fixed solver per method."""

    def optimize(
        self,
        request: PortfolioOptimizationRequest,
    ) -> PortfolioOptimizationResult:
        """Construct target weights or return structured failure evidence."""
        try:
            prepared = prepare_input(request)
        except OptimizationInputError as exc:
            return self._failure(request, exc.code, str(exc))
        try:
            values, solver, status, objective = self._solve(request, prepared)
        except (_cp.error.SolverError, ValueError, ArithmeticError) as exc:
            return self._failure(request, "solver_error", str(exc))
        if status != _cp.OPTIMAL or values is None:
            return self._failure(
                request,
                "solver_not_optimal",
                f"{solver} returned {status}",
                solver=solver,
                solver_status=str(status),
            )
        weights = np.zeros(len(request.instrument_ids), dtype=float)
        weights[list(prepared.indices)] = np.maximum(values, 0.0)
        violations = self._constraint_violations(request, weights)
        if violations:
            return self._failure(
                request,
                "constraint_violation",
                ", ".join(violations),
                solver=solver,
                solver_status=status,
                violations=violations,
            )
        local_contributions, contribution_error = self._risk_contributions(
            weights[list(prepared.indices)],
            prepared.covariance,
            request.policy.method,
        )
        contributions = _expand_contributions(
            local_contributions,
            prepared.indices,
            len(request.instrument_ids),
        )
        if self._risk_budget_failed(request, contribution_error):
            diagnostic = (
                "unavailable"
                if contribution_error is None
                else f"{contribution_error:.8g}"
            )
            return self._failure(
                request,
                "risk_budget_not_reconciled",
                f"risk contribution error {diagnostic}",
                solver=solver,
                solver_status=status,
            )
        return PortfolioOptimizationResult(
            success=True,
            weights=tuple(float(value) for value in weights),
            solver=solver,
            solver_version=_solver_version(solver),
            solver_status=status,
            policy_digest=request.policy.digest,
            source_snapshot_ids=request.source_snapshot_ids,
            objective_value=objective,
            covariance_repaired=prepared.covariance_repaired,
            risk_contributions=contributions,
            risk_contribution_error=contribution_error,
        )

    def _solve(
        self,
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
    ) -> tuple[np.ndarray | None, str, str, float | None]:
        minimum = request.policy.min_weight
        if minimum <= 0.0:
            return self._solve_fixed_universe(request, prepared, minimum_weight=0.0)
        initial = self._solve_fixed_universe(
            request,
            prepared,
            minimum_weight=0.0,
        )
        initial_values, solver, status, objective = initial
        if status != _cp.OPTIMAL or initial_values is None:
            return initial
        active = _deterministic_active_set(
            request,
            prepared,
            initial_values,
        )
        if len(active) == len(initial_values):
            return initial
        if not active:
            return None, solver, "active_set_empty", objective
        active_prepared = subset_prepared_input(prepared, active)
        active_values, solver, status, objective = self._solve_fixed_universe(
            request,
            active_prepared,
            minimum_weight=minimum,
        )
        if active_values is None:
            return None, solver, status, objective
        expanded = np.zeros(len(prepared.indices), dtype=float)
        expanded[list(active)] = active_values
        return expanded, solver, status, objective

    def _solve_fixed_universe(
        self,
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
        *,
        minimum_weight: float,
    ) -> tuple[np.ndarray | None, str, str, float | None]:
        if request.policy.method is OptimizationMethod.RISK_PARITY:
            return self._solve_risk_parity(
                request,
                prepared,
                minimum_weight=minimum_weight,
            )
        count = len(prepared.indices)
        weights: Variable = _cp.Variable(count)
        constraints = self._standard_constraints(
            request,
            prepared,
            weights,
            minimum_weight=minimum_weight,
        )
        excluded_turnover = _excluded_turnover(request, prepared)
        turnover_cost = (
            request.policy.turnover_penalty_bps
            / 10_000.0
            * (_cp.norm1(weights - prepared.current) + excluded_turnover)
        )
        objective_expression, solver = self._standard_objective(
            request,
            prepared,
            weights,
            constraints,
        )
        problem: Problem = _cp.Problem(
            _cp.Minimize(objective_expression + turnover_cost),
            constraints,
        )
        self._run_solver(problem, solver, request.policy.solver_timeout_seconds)
        values = (
            None if weights.value is None else np.asarray(weights.value, dtype=float)
        )
        objective = _solver_float(cast(object | None, problem.value))
        return values, solver, str(problem.status), objective

    @staticmethod
    def _standard_objective(
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
        weights: Variable,
        constraints: list[Constraint],
    ) -> tuple[Expression, str]:
        if request.policy.method is OptimizationMethod.MVO:
            expression = _cp.quad_form(weights, prepared.covariance)
            if prepared.expected is not None:
                expression -= prepared.expected @ weights
            return expression, "OSQP"
        scenarios = prepared.scenarios
        if scenarios is None or scenarios.shape[0] < _MINIMUM_SCENARIOS:
            raise ValueError("historical CVaR requires scenario_returns")
        threshold: Variable = _cp.Variable()
        excess: Variable = _cp.Variable(scenarios.shape[0], nonneg=True)
        losses = -(scenarios @ weights)
        constraints.append(excess >= losses - threshold)
        tail_scale = 1.0 / (
            scenarios.shape[0] * (1.0 - request.policy.confidence_level)
        )
        return threshold + tail_scale * _cp.sum(excess), "CLARABEL"

    def _solve_risk_parity(
        self,
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
        *,
        minimum_weight: float,
    ) -> tuple[np.ndarray | None, str, str, float | None]:
        count = len(prepared.indices)
        scale_weights: Variable = _cp.Variable(count, pos=True)
        total_scale: Expression = _cp.sum(scale_weights)
        investable = 1.0 - request.policy.cash_target
        constraints: list[Constraint] = [
            scale_weights <= (request.policy.max_weight / investable) * total_scale
        ]
        if minimum_weight > 0.0:
            constraints.append(
                scale_weights >= (minimum_weight / investable) * total_scale
            )
        if request.policy.max_turnover is not None:
            remaining_turnover = request.policy.max_turnover - _excluded_turnover(
                request, prepared
            )
            constraints.append(
                _cp.norm1(investable * scale_weights - prepared.current * total_scale)
                <= remaining_turnover * total_scale
            )
        self._industry_constraints(
            request,
            prepared,
            scale_weights,
            constraints,
            total_scale=total_scale,
        )
        budgets = np.full(count, 1.0 / count)
        objective = _cp.Minimize(
            0.5 * _cp.quad_form(scale_weights, prepared.covariance)
            - budgets @ _cp.log(scale_weights)
        )
        problem: Problem = _cp.Problem(objective, constraints)
        self._run_solver(
            problem,
            "CLARABEL",
            request.policy.solver_timeout_seconds,
        )
        values = None
        if scale_weights.value is not None:
            raw = np.asarray(scale_weights.value, dtype=float)
            values = investable * raw / raw.sum()
        objective_value = _solver_float(cast(object | None, problem.value))
        return values, "CLARABEL", str(problem.status), objective_value

    @staticmethod
    def _run_solver(
        problem: Problem,
        solver: str,
        timeout_seconds: float,
    ) -> None:
        options: dict[str, float | bool] = {"time_limit": timeout_seconds}
        if solver == "OSQP":
            options.update(eps_abs=1e-9, eps_rel=1e-9, polishing=True)
        _cp.Problem.solve(problem, solver=solver, verbose=False, **options)

    def _standard_constraints(
        self,
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
        weights: Variable,
        *,
        minimum_weight: float,
    ) -> list[Constraint]:
        policy = request.policy
        constraints: list[Constraint] = [
            weights >= minimum_weight,
            weights <= policy.max_weight,
            _cp.sum(weights) == 1.0 - policy.cash_target,
        ]
        if policy.max_turnover is not None:
            constraints.append(
                _cp.norm1(weights - prepared.current)
                + _excluded_turnover(request, prepared)
                <= policy.max_turnover
            )
        self._industry_constraints(
            request,
            prepared,
            weights,
            constraints,
            total_scale=None,
        )
        return constraints

    @staticmethod
    def _industry_constraints(
        request: PortfolioOptimizationRequest,
        prepared: PreparedOptimizationInput,
        weights: Variable,
        constraints: list[Constraint],
        *,
        total_scale: Expression | None,
    ) -> None:
        if not request.policy.industry_caps:
            return
        if prepared.industries is None:
            raise ValueError("industry caps require industries")
        investable = 1.0 - request.policy.cash_target
        for industry, cap in request.policy.industry_caps:
            mask = np.asarray(
                [value == industry for value in prepared.industries],
                dtype=float,
            )
            if total_scale is None:
                constraints.append(mask @ weights <= cap)
            else:
                constraints.append(mask @ weights <= (cap / investable) * total_scale)

    @staticmethod
    def _constraint_violations(
        request: PortfolioOptimizationRequest,
        weights: np.ndarray,
    ) -> tuple[str, ...]:
        policy = request.policy
        tolerance = policy.constraint_tolerance
        violations: list[str] = []
        if abs(float(weights.sum()) - (1.0 - policy.cash_target)) > tolerance:
            violations.append("total_weight")
        if float(weights.min(initial=0.0)) < -tolerance:
            violations.append("long_only")
        if float(weights.max(initial=0.0)) > policy.max_weight + tolerance:
            violations.append("max_weight")
        positive = weights[weights > tolerance]
        if positive.size and float(positive.min()) < policy.min_weight - tolerance:
            violations.append("min_weight")
        if _turnover_exceeded(request, weights, tolerance):
            violations.append("max_turnover")
        violations.extend(_industry_violations(request, weights, tolerance))
        return tuple(violations)

    @staticmethod
    def _risk_contributions(
        weights: np.ndarray,
        covariance: np.ndarray,
        method: OptimizationMethod,
    ) -> tuple[tuple[float, ...] | None, float | None]:
        if not np.any(weights):
            return None, None
        absolute = weights * (covariance @ weights)
        total = float(absolute.sum())
        if total <= 0.0:
            return None, None
        shares = absolute / total
        error = None
        if method is OptimizationMethod.RISK_PARITY:
            active = weights > _ACTIVE_WEIGHT_TOLERANCE
            target = 1.0 / int(active.sum())
            error = float(np.max(np.abs(shares[active] - target)))
        return tuple(float(value) for value in shares), error

    @staticmethod
    def _risk_budget_failed(
        request: PortfolioOptimizationRequest,
        contribution_error: float | None,
    ) -> bool:
        return bool(
            request.policy.method is OptimizationMethod.RISK_PARITY
            and (
                contribution_error is None
                or contribution_error > request.policy.risk_contribution_tolerance
            )
        )

    @staticmethod
    def _failure(
        request: PortfolioOptimizationRequest,
        code: str,
        message: str,
        *,
        solver: str = "",
        solver_status: str = "failed",
        violations: tuple[str, ...] = (),
    ) -> PortfolioOptimizationResult:
        return PortfolioOptimizationResult(
            success=False,
            weights=(),
            solver=solver,
            solver_version=_solver_version(solver) if solver else "",
            solver_status=solver_status,
            policy_digest=request.policy.digest,
            source_snapshot_ids=request.source_snapshot_ids,
            constraint_violations=violations,
            failure_code=code,
            failure_message=message,
        )


def _turnover_exceeded(
    request: PortfolioOptimizationRequest,
    weights: np.ndarray,
    tolerance: float,
) -> bool:
    maximum = request.policy.max_turnover
    if maximum is None:
        return False
    turnover = float(
        np.abs(weights - np.asarray(request.current_weights, dtype=float)).sum()
    )
    return turnover > maximum + tolerance


def _expand_contributions(
    contributions: tuple[float, ...] | None,
    active_indices: tuple[int, ...],
    full_count: int,
) -> tuple[float, ...] | None:
    """Expand solver-universe risk shares to the public request universe."""
    if contributions is None:
        return None
    expanded = np.zeros(full_count, dtype=float)
    expanded[list(active_indices)] = np.asarray(contributions, dtype=float)
    return tuple(float(value) for value in expanded)


def _excluded_turnover(
    request: PortfolioOptimizationRequest,
    prepared: PreparedOptimizationInput,
) -> float:
    selected = set(prepared.indices)
    return sum(
        abs(float(weight))
        for index, weight in enumerate(request.current_weights)
        if index not in selected
    )


def _deterministic_active_set(
    request: PortfolioOptimizationRequest,
    prepared: PreparedOptimizationInput,
    initial_values: np.ndarray,
) -> tuple[int, ...]:
    """Choose a feasible-size MinWeight universe with stable tie breaking."""
    policy = request.policy
    minimum = policy.min_weight
    investable = 1.0 - policy.cash_target
    tolerance = policy.constraint_tolerance
    maximum_count = min(
        len(initial_values),
        math.floor((investable + tolerance) / minimum),
    )
    if maximum_count < 1:
        return ()
    ranked = sorted(
        range(len(initial_values)),
        key=lambda index: (
            -float(initial_values[index]),
            request.instrument_ids[prepared.indices[index]],
        ),
    )
    selected = {
        index
        for index, value in enumerate(initial_values)
        if value >= minimum - tolerance
    }
    if len(selected) > maximum_count:
        selected = set([index for index in ranked if index in selected][:maximum_count])
    required_count = math.ceil((investable - tolerance) / policy.max_weight)
    target_count = max(
        required_count,
        len(selected) if selected else maximum_count,
    )
    if target_count > maximum_count:
        return ()
    for index in ranked:
        if len(selected) >= target_count:
            break
        selected.add(index)
    return tuple(sorted(selected))


def _industry_violations(
    request: PortfolioOptimizationRequest,
    weights: np.ndarray,
    tolerance: float,
) -> list[str]:
    if not request.policy.industry_caps or request.industries is None:
        return []
    violations: list[str] = []
    for industry, cap in request.policy.industry_caps:
        exposure = sum(
            weight
            for weight, value in zip(weights, request.industries, strict=True)
            if value == industry
        )
        if exposure > cap + tolerance:
            violations.append(f"industry_cap:{industry}")
    return violations


def _solver_float(value: object | None) -> float | None:
    """Validate a scalar returned by the dynamically typed CVXPY boundary."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | np.floating):
        raise ArithmeticError("solver objective must be a real scalar")
    result = float(cast("int | float", value))
    if not np.isfinite(result):
        raise ArithmeticError("solver objective must be finite")
    return result


def _solver_version(solver: str) -> str:
    package = {"OSQP": "osqp", "CLARABEL": "clarabel"}[solver]
    return version(package)
