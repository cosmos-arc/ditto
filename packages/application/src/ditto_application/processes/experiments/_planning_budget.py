"""Typed resource-budget inputs and pure estimates for experiment planning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from ditto_application.processes.experiments._planning_values import (
    planning_error as _planning_error,
)

__all__ = [
    "ExperimentBudgetSpec",
    "ExperimentTrack",
    "ResourceCostModel",
    "ResourceEstimate",
    "ValidationWorkload",
    "estimate_resource_budget",
]

_MAX_CANDIDATES = 128
_VALIDATION_FOLD_COUNT = 3


class ExperimentTrack(StrEnum):
    """Whether one plan may reserve the one-shot promotion holdout run."""

    PROMOTION = "promotion"
    RESEARCH_ONLY = "research_only"


def _positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        _planning_error(
            f"{field_name} must be a positive integer",
            reason="invalid_positive_integer",
            field=field_name,
            value=value,
        )
    return value


def nonnegative_int(value: object, *, field_name: str) -> int:
    """Validate one exact non-negative integer for a parent planning graph."""
    if type(value) is not int or value < 0:
        _planning_error(
            f"{field_name} must be a non-negative integer",
            reason="invalid_nonnegative_integer",
            field=field_name,
            value=value,
        )
    return value


@dataclass(frozen=True, slots=True)
class ValidationWorkload:
    """Narrow session-count input supplied by the validation compiler."""

    fold_session_counts: Sequence[int]
    holdout_session_count: int

    def __post_init__(self) -> None:
        """Require the three persisted pre-selection folds and reserved holdout."""
        if type(self) is not ValidationWorkload:
            _planning_error(
                "workload must be an exact ValidationWorkload",
                reason="invalid_validation_workload",
            )
        raw_counts = cast("object", self.fold_session_counts)
        if type(raw_counts) not in (tuple, list):
            _planning_error(
                "fold_session_counts must be an explicit three-item list",
                reason="invalid_fold_session_counts",
            )
        counts = tuple(cast("Sequence[object]", raw_counts))
        if len(counts) != _VALIDATION_FOLD_COUNT or any(
            type(count) is not int or count <= 0 for count in counts
        ):
            _planning_error(
                "fold_session_counts must contain three positive integers",
                reason="invalid_fold_session_counts",
                fold_session_counts=counts,
            )
        object.__setattr__(self, "fold_session_counts", cast("tuple[int, ...]", counts))
        _positive_int(
            self.holdout_session_count,
            field_name="holdout_session_count",
        )


@dataclass(frozen=True, slots=True)
class ResourceCostModel:
    """Deterministic disk-estimation coefficients frozen before launch."""

    bytes_per_run: int
    bytes_per_trading_session: int

    def __post_init__(self) -> None:
        """Reject implicit, negative, or non-integral cost coefficients."""
        if type(self) is not ResourceCostModel:
            _planning_error(
                "cost model must be an exact ResourceCostModel",
                reason="invalid_resource_cost_model",
            )
        nonnegative_int(self.bytes_per_run, field_name="bytes_per_run")
        nonnegative_int(
            self.bytes_per_trading_session,
            field_name="bytes_per_trading_session",
        )


@dataclass(frozen=True, slots=True)
class ExperimentBudgetSpec:
    """Explicit hard resource ceilings pre-registered for one experiment."""

    candidate_limit: int
    fold_run_limit: int
    trading_session_limit: int
    disk_byte_limit: int

    def __post_init__(self) -> None:
        """Validate positive bounded ceilings without inventing environment defaults."""
        if type(self) is not ExperimentBudgetSpec:
            _planning_error(
                "budget must be an exact ExperimentBudgetSpec",
                reason="invalid_experiment_budget",
            )
        _positive_int(self.candidate_limit, field_name="candidate_limit")
        if self.candidate_limit > _MAX_CANDIDATES:
            _planning_error(
                "candidate_limit cannot exceed 128",
                reason="invalid_candidate_limit",
                candidate_limit=self.candidate_limit,
            )
        _positive_int(self.fold_run_limit, field_name="fold_run_limit")
        _positive_int(
            self.trading_session_limit,
            field_name="trading_session_limit",
        )
        _positive_int(self.disk_byte_limit, field_name="disk_byte_limit")


@dataclass(frozen=True, slots=True)
class ResourceEstimate:
    """Pure deterministic run, session, and disk estimate."""

    candidate_count: int
    validation_run_count: int
    holdout_run_count: int
    total_run_count: int
    estimated_trading_sessions: int
    estimated_disk_bytes: int


def estimate_resource_budget(
    *,
    candidate_count: int,
    track: ExperimentTrack,
    workload: ValidationWorkload,
    cost_model: ResourceCostModel,
) -> ResourceEstimate:
    """Estimate bounded work without reading calendars, storage, or runtime state."""
    _positive_int(candidate_count, field_name="candidate_count")
    if type(cast("object", track)) is not ExperimentTrack:
        _planning_error(
            "track must be ExperimentTrack",
            reason="invalid_experiment_track",
        )
    if type(cast("object", workload)) is not ValidationWorkload:
        _planning_error(
            "workload must be ValidationWorkload",
            reason="invalid_validation_workload",
        )
    if type(cast("object", cost_model)) is not ResourceCostModel:
        _planning_error(
            "cost_model must be ResourceCostModel",
            reason="invalid_resource_cost_model",
        )
    validation_runs = _VALIDATION_FOLD_COUNT * candidate_count
    holdout_runs = 1 if track is ExperimentTrack.PROMOTION else 0
    validation_sessions = candidate_count * sum(workload.fold_session_counts)
    holdout_sessions = workload.holdout_session_count if holdout_runs else 0
    total_runs = validation_runs + holdout_runs
    total_sessions = validation_sessions + holdout_sessions
    disk_bytes = (
        total_runs * cost_model.bytes_per_run
        + total_sessions * cost_model.bytes_per_trading_session
    )
    return ResourceEstimate(
        candidate_count=candidate_count,
        validation_run_count=validation_runs,
        holdout_run_count=holdout_runs,
        total_run_count=total_runs,
        estimated_trading_sessions=total_sessions,
        estimated_disk_bytes=disk_bytes,
    )
