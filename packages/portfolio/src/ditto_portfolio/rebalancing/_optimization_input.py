"""Validation and normalization for optimizer provider inputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioOptimizationRequest,
)

__all__ = [
    "OptimizationInputError",
    "PreparedOptimizationInput",
    "prepare_input",
    "subset_prepared_input",
]

_PSD_REJECTION_TOLERANCE = -1e-8
_PSD_FLOOR = 1e-12
_MATRIX_DIMENSIONS = 2


class OptimizationInputError(ValueError):
    """Structured invalid optimizer input."""

    def __init__(self, code: str, message: str) -> None:
        """Store a stable failure code beside the diagnostic message."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreparedOptimizationInput:
    """Validated arrays restricted to the deterministic active universe."""

    indices: tuple[int, ...]
    covariance: np.ndarray
    scenarios: np.ndarray | None
    current: np.ndarray
    expected: np.ndarray | None
    industries: tuple[str | None, ...] | None
    covariance_repaired: bool


def prepare_input(request: PortfolioOptimizationRequest) -> PreparedOptimizationInput:
    """Validate a request and return solver-ready active-universe arrays."""
    count = _validate_common(request)
    indices = _select_indices(request, count)
    covariance, repaired = _prepare_covariance(request, indices, count)
    return PreparedOptimizationInput(
        indices=indices,
        covariance=covariance,
        scenarios=_prepare_scenarios(request, indices, count),
        current=np.asarray(request.current_weights, dtype=float)[list(indices)],
        expected=_prepare_expected(request, indices, count),
        industries=_prepare_industries(request, indices, count),
        covariance_repaired=repaired,
    )


def subset_prepared_input(
    prepared: PreparedOptimizationInput,
    local_indices: tuple[int, ...],
) -> PreparedOptimizationInput:
    """Return a deterministic active-set subset of an already validated input."""
    if not local_indices or len(set(local_indices)) != len(local_indices):
        raise ValueError("active-set indices must be non-empty and unique")
    if min(local_indices) < 0 or max(local_indices) >= len(prepared.indices):
        raise ValueError("active-set index is out of bounds")
    selected = list(local_indices)
    return PreparedOptimizationInput(
        indices=tuple(prepared.indices[index] for index in local_indices),
        covariance=prepared.covariance[np.ix_(selected, selected)],
        scenarios=(
            None if prepared.scenarios is None else prepared.scenarios[:, selected]
        ),
        current=prepared.current[selected],
        expected=(None if prepared.expected is None else prepared.expected[selected]),
        industries=(
            None
            if prepared.industries is None
            else tuple(prepared.industries[index] for index in local_indices)
        ),
        covariance_repaired=prepared.covariance_repaired,
    )


def _validate_common(request: PortfolioOptimizationRequest) -> int:
    count = len(request.instrument_ids)
    if count > request.policy.max_candidates:
        raise OptimizationInputError(
            "candidate_capacity_exceeded",
            f"{count} candidates exceeds {request.policy.max_candidates}",
        )
    if count == 0 or len(set(request.instrument_ids)) != count:
        raise OptimizationInputError("invalid_universe", "invalid instrument ids")
    if (
        not request.source_snapshot_ids
        or any(not value.strip() for value in request.source_snapshot_ids)
        or len(set(request.source_snapshot_ids)) != len(request.source_snapshot_ids)
    ):
        raise OptimizationInputError(
            "missing_snapshot",
            "source snapshots must be non-empty and unique",
        )
    if len(request.candidate_weights) != count:
        raise OptimizationInputError("shape_mismatch", "candidate weight shape")
    if len(request.current_weights) != count:
        raise OptimizationInputError("shape_mismatch", "current weight shape")
    _validate_weights(request)
    return count


def _validate_weights(request: PortfolioOptimizationRequest) -> None:
    """Reject invalid portfolio weights before they reach a solver boundary."""
    tolerance = request.policy.constraint_tolerance
    for name, values in (
        ("candidate", request.candidate_weights),
        ("current", request.current_weights),
    ):
        weights = np.asarray(values, dtype=float)
        if not np.isfinite(weights).all() or bool(np.any(weights < 0.0)):
            raise OptimizationInputError(
                "invalid_weights",
                f"{name} weights must be finite and non-negative",
            )
        if float(weights.sum()) > 1.0 + tolerance:
            raise OptimizationInputError(
                "invalid_weights",
                f"{name} weights cannot exceed total portfolio weight",
            )


def _select_indices(
    request: PortfolioOptimizationRequest,
    count: int,
) -> tuple[int, ...]:
    eligible = (
        request.eligible
        if request.eligible is not None
        else tuple(True for _ in range(count))
    )
    if len(eligible) != count:
        raise OptimizationInputError("shape_mismatch", "eligible shape")
    indices = [index for index, allowed in enumerate(eligible) if allowed]
    max_positions = request.policy.max_positions
    if max_positions is not None and len(indices) > max_positions:
        indices = sorted(
            indices,
            key=lambda index: (
                -request.candidate_weights[index],
                request.instrument_ids[index],
            ),
        )[:max_positions]
        indices.sort()
    if not indices:
        raise OptimizationInputError("empty_eligible_universe", "no eligible assets")
    return tuple(indices)


def _prepare_covariance(
    request: PortfolioOptimizationRequest,
    indices: tuple[int, ...],
    count: int,
) -> tuple[np.ndarray, bool]:
    covariance = np.asarray(request.covariance, dtype=float)
    if covariance.shape != (count, count) or not np.isfinite(covariance).all():
        raise OptimizationInputError("invalid_covariance", "invalid shape or values")
    selected = covariance[np.ix_(indices, indices)]
    selected = (selected + selected.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(selected)
    minimum = float(eigenvalues.min())
    if minimum < _PSD_REJECTION_TOLERANCE:
        raise OptimizationInputError("covariance_not_psd", "negative eigenvalue")
    repaired = minimum < _PSD_FLOOR
    if repaired:
        eigenvalues = np.maximum(eigenvalues, _PSD_FLOOR)
        selected = (eigenvectors * eigenvalues) @ eigenvectors.T
    return selected, repaired


def _prepare_scenarios(
    request: PortfolioOptimizationRequest,
    indices: tuple[int, ...],
    count: int,
) -> np.ndarray | None:
    if request.scenario_returns is None:
        if request.policy.method is OptimizationMethod.HISTORICAL_CVAR:
            raise OptimizationInputError(
                "insufficient_scenarios",
                "historical CVaR requires scenario returns",
            )
        return None
    scenarios = np.asarray(request.scenario_returns, dtype=float)
    if scenarios.ndim != _MATRIX_DIMENSIONS or scenarios.shape[1] != count:
        raise OptimizationInputError("shape_mismatch", "scenario shape")
    if not np.isfinite(scenarios).all():
        raise OptimizationInputError("invalid_scenarios", "non-finite scenarios")
    if (
        request.policy.method is OptimizationMethod.HISTORICAL_CVAR
        and scenarios.shape[0] < request.policy.min_observations
    ):
        raise OptimizationInputError(
            "insufficient_scenarios",
            " ".join(
                (
                    "historical CVaR requires at least",
                    str(request.policy.min_observations),
                    "scenarios",
                )
            ),
        )
    return scenarios[:, list(indices)]


def _prepare_expected(
    request: PortfolioOptimizationRequest,
    indices: tuple[int, ...],
    count: int,
) -> np.ndarray | None:
    if request.expected_returns is None:
        return None
    if len(request.expected_returns) != count:
        raise OptimizationInputError("shape_mismatch", "expected return shape")
    expected = np.asarray(request.expected_returns, dtype=float)
    if not np.isfinite(expected).all():
        raise OptimizationInputError("invalid_expected_returns", "non-finite values")
    return expected[list(indices)]


def _prepare_industries(
    request: PortfolioOptimizationRequest,
    indices: tuple[int, ...],
    count: int,
) -> tuple[str | None, ...] | None:
    if request.industries is None:
        if request.policy.industry_caps:
            raise OptimizationInputError(
                "missing_industries",
                "industry caps require industries",
            )
        return None
    if len(request.industries) != count:
        raise OptimizationInputError("shape_mismatch", "industry shape")
    selected = tuple(request.industries[index] for index in indices)
    if request.policy.industry_caps and any(
        industry is None or not industry.strip() for industry in selected
    ):
        raise OptimizationInputError(
            "missing_industries",
            "industry caps require complete industry mapping",
        )
    return selected
