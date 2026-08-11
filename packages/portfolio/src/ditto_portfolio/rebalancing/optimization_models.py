"""Public R4 portfolio construction contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Protocol

import numpy as np
from ditto_kernel.identity import InstrumentId

__all__ = [
    "OptimizationMethod",
    "PortfolioConstructionPolicy",
    "PortfolioOptimizationRequest",
    "PortfolioOptimizationResult",
    "PortfolioOptimizer",
]

MAX_CANDIDATES = 500
MINIMUM_COVARIANCE_OBSERVATIONS = 2


class OptimizationMethod(StrEnum):
    """Supported R4 portfolio construction methods."""

    MVO = "mvo"
    HISTORICAL_CVAR = "historical_cvar"
    RISK_PARITY = "risk_parity"


@dataclass(frozen=True)
class PortfolioConstructionPolicy:
    """Versioned, deterministic optimization policy."""

    policy_id: str
    version: int
    method: OptimizationMethod
    execution_mode: Literal["shadow", "enforced"] = "enforced"
    lookback_sessions: int = 250
    min_observations: int = 60
    confidence_level: float = 0.99
    turnover_penalty_bps: float = 10.0
    max_candidates: int = MAX_CANDIDATES
    cash_target: float = 0.0
    max_weight: float = 1.0
    min_weight: float = 0.0
    max_positions: int | None = None
    max_turnover: float | None = None
    industry_caps: tuple[tuple[str, float], ...] = ()
    solver_timeout_seconds: float = 10.0
    constraint_tolerance: float = 1e-6
    risk_contribution_tolerance: float = 1e-4

    def __post_init__(self) -> None:
        """Reject invalid or unsafe policy values."""
        _validate_policy_identity(self)
        _validate_policy_bounds(self)
        _validate_policy_limits(self)

    @property
    def digest(self) -> str:
        """Return a stable digest for run evidence."""
        fields = (
            self.policy_id,
            str(self.version),
            self.method.value,
            self.execution_mode,
            str(self.lookback_sessions),
            str(self.min_observations),
            f"{self.confidence_level:.12g}",
            f"{self.turnover_penalty_bps:.12g}",
            str(self.max_candidates),
            f"{self.cash_target:.12g}",
            f"{self.max_weight:.12g}",
            f"{self.min_weight:.12g}",
            str(self.max_positions),
            str(self.max_turnover),
            repr(tuple(sorted(self.industry_caps))),
            f"{self.solver_timeout_seconds:.12g}",
            f"{self.constraint_tolerance:.12g}",
            f"{self.risk_contribution_tolerance:.12g}",
        )
        return sha256("|".join(fields).encode()).hexdigest()


@dataclass(frozen=True)
class PortfolioOptimizationRequest:
    """Optimizer inputs assembled by an orchestration layer."""

    policy: PortfolioConstructionPolicy
    instrument_ids: tuple[InstrumentId, ...]
    covariance: np.ndarray
    scenario_returns: np.ndarray | None
    candidate_weights: tuple[float, ...]
    current_weights: tuple[float, ...]
    source_snapshot_ids: tuple[str, ...]
    expected_returns: tuple[float, ...] | None = None
    industries: tuple[str | None, ...] | None = None
    eligible: tuple[bool, ...] | None = None


@dataclass(frozen=True)
class PortfolioOptimizationResult:
    """Structured success or fail-closed optimization evidence."""

    success: bool
    weights: tuple[float, ...]
    solver: str
    solver_version: str
    solver_status: str
    policy_digest: str
    source_snapshot_ids: tuple[str, ...]
    constraint_violations: tuple[str, ...] = ()
    failure_code: str | None = None
    failure_message: str | None = None
    objective_value: float | None = None
    covariance_repaired: bool = False
    risk_contributions: tuple[float, ...] | None = None
    risk_contribution_error: float | None = None


class PortfolioOptimizer(Protocol):
    """Consumer-facing optimization provider contract."""

    def optimize(
        self,
        request: PortfolioOptimizationRequest,
    ) -> PortfolioOptimizationResult:
        """Construct target weights or return structured failure evidence."""
        ...


def _validate_policy_identity(policy: PortfolioConstructionPolicy) -> None:
    if not policy.policy_id.strip():
        raise ValueError("policy_id must be non-empty")
    if policy.version < 1:
        raise ValueError("version must be positive")
    if policy.execution_mode not in {"shadow", "enforced"}:
        raise ValueError("execution_mode must be shadow or enforced")
    if policy.lookback_sessions < policy.min_observations:
        raise ValueError("lookback_sessions must cover min_observations")
    if policy.min_observations < MINIMUM_COVARIANCE_OBSERVATIONS:
        raise ValueError("min_observations must be at least 2")


def _validate_policy_bounds(policy: PortfolioConstructionPolicy) -> None:
    if not 0.0 <= policy.cash_target < 1.0:
        raise ValueError("cash_target must be in [0, 1)")
    if not 0.0 < policy.max_weight <= 1.0:
        raise ValueError("max_weight must be in (0, 1]")
    if not 0.0 <= policy.min_weight <= policy.max_weight:
        raise ValueError("min_weight must be in [0, max_weight]")
    if not 0.0 < policy.confidence_level < 1.0:
        raise ValueError("confidence_level must be in (0, 1)")
    for industry, cap in policy.industry_caps:
        if not industry.strip() or not 0.0 <= cap <= 1.0:
            raise ValueError("industry caps require a name and weight in [0, 1]")


def _validate_policy_limits(policy: PortfolioConstructionPolicy) -> None:
    finite_values = (
        policy.turnover_penalty_bps,
        policy.solver_timeout_seconds,
        policy.constraint_tolerance,
        policy.risk_contribution_tolerance,
        *((policy.max_turnover,) if policy.max_turnover is not None else ()),
    )
    if not all(math.isfinite(value) for value in finite_values):
        raise ValueError("portfolio policy numeric limits must be finite")
    if policy.turnover_penalty_bps < 0.0:
        raise ValueError("turnover_penalty_bps cannot be negative")
    if not 1 <= policy.max_candidates <= MAX_CANDIDATES:
        raise ValueError(f"max_candidates must be in [1, {MAX_CANDIDATES}]")
    if policy.max_positions is not None and policy.max_positions < 1:
        raise ValueError("max_positions must be positive")
    if policy.max_turnover is not None and policy.max_turnover < 0.0:
        raise ValueError("max_turnover cannot be negative")
    if policy.solver_timeout_seconds <= 0.0:
        raise ValueError("solver_timeout_seconds must be positive")
    if policy.constraint_tolerance <= 0.0:
        raise ValueError("constraint_tolerance must be positive")
    if policy.risk_contribution_tolerance <= 0.0:
        raise ValueError("risk_contribution_tolerance must be positive")
