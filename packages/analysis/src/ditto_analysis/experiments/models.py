"""Pure experiment control-plane identities, states, and records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import (
    ExperimentIdentityError,
    ExperimentSpecError,
    ExperimentStateTransitionError,
)

__all__ = [
    "AttemptId",
    "AttemptRecord",
    "BacktestRunId",
    "CandidateId",
    "CandidateRecord",
    "CheckpointRef",
    "ContentHash",
    "ExperimentDesiredState",
    "ExperimentFailureCode",
    "ExperimentId",
    "ExperimentRecord",
    "ExperimentStage",
    "ExperimentStatus",
    "FoldId",
    "FoldRecord",
    "SnapshotId",
    "StrategyVersion",
    "validate_status_transition",
]

_SHA256_HEX_LENGTH = 64


def _identity_error(identity_name: str, value: object) -> ExperimentIdentityError:
    return ExperimentIdentityError(
        f"{identity_name} must be a non-empty opaque string",
        details={
            "reason_code": "invalid_experiment_identity",
            "identity_type": identity_name,
            "value": value,
        },
    )


@dataclass(frozen=True, slots=True)
class _OpaqueIdentity:
    """Base for nominal, opaque experiment identity values."""

    value: str

    def __post_init__(self) -> None:
        """Reject blank, padded, and non-string identities."""
        raw_value = cast("object", self.value)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise _identity_error(type(self).__name__, self.value)
        if self.value != self.value.strip():
            raise _identity_error(type(self).__name__, self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ExperimentId(_OpaqueIdentity):
    """Opaque experiment identity."""


@dataclass(frozen=True, slots=True)
class CandidateId(_OpaqueIdentity):
    """Opaque candidate identity."""


@dataclass(frozen=True, slots=True)
class FoldId(_OpaqueIdentity):
    """Opaque walk-forward fold identity."""


@dataclass(frozen=True, slots=True)
class AttemptId(_OpaqueIdentity):
    """Opaque immutable execution-attempt identity."""


@dataclass(frozen=True, slots=True)
class SnapshotId(_OpaqueIdentity):
    """Opaque certified research snapshot identity."""


@dataclass(frozen=True, slots=True)
class StrategyVersion(_OpaqueIdentity):
    """Opaque frozen strategy version identity."""


@dataclass(frozen=True, slots=True)
class BacktestRunId(_OpaqueIdentity):
    """Opaque backtest run identity without a backtest package dependency."""


@dataclass(frozen=True, slots=True)
class CheckpointRef(_OpaqueIdentity):
    """Opaque checkpoint reference without persistence semantics."""


@dataclass(frozen=True, slots=True)
class ContentHash:
    """Validated lowercase SHA-256 content hash."""

    value: str

    def __post_init__(self) -> None:
        """Validate the canonical SHA-256 representation."""
        raw_value = cast("object", self.value)
        if (
            not isinstance(raw_value, str)
            or len(raw_value) != _SHA256_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in raw_value)
        ):
            raise ExperimentIdentityError(
                "content hash must be a lowercase SHA-256 hex digest",
                details={
                    "reason_code": "invalid_content_hash",
                    "value": self.value,
                },
            )

    def __str__(self) -> str:
        """Return the canonical digest."""
        return self.value


class ExperimentStatus(StrEnum):
    """Observed, durable experiment lifecycle status."""

    DRAFT = "draft"
    BLOCKED = "blocked"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED = "failed"


class ExperimentDesiredState(StrEnum):
    """Operator intent, deliberately separate from observed status."""

    RUN = "run"
    PAUSE = "pause"
    CANCEL = "cancel"


class ExperimentStage(StrEnum):
    """Independent research stage, not a lifecycle status."""

    PREFLIGHT = "preflight"
    EXPLORATION = "exploration"
    WALK_FORWARD = "walk_forward"
    CANDIDATE_SELECTION = "candidate_selection"
    HOLDOUT = "holdout"
    EVIDENCE = "evidence"


class ExperimentFailureCode(StrEnum):
    """Stable machine-readable experiment failure classifications."""

    PREFLIGHT_FAILED = "preflight_failed"
    CANDIDATE_FAILED = "candidate_failed"
    INPUT_HASH_MISMATCH = "input_hash_mismatch"
    LEASE_LOST = "lease_lost"
    SYSTEM_ERROR = "system_error"


def _require_positive_ordinal(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ExperimentSpecError(
            f"{field_name} must be a positive integer",
            details={
                "reason_code": "invalid_ordinal",
                "field": field_name,
                "value": value,
            },
        )
    return value


def _require_utc(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ExperimentSpecError(
            f"{field_name} must be an aware UTC datetime",
            details={
                "reason_code": "datetime_not_utc",
                "field": field_name,
            },
        )
    return value


def _require_instance(value: object, expected: type, field_name: str) -> None:
    if not isinstance(value, expected):
        raise ExperimentSpecError(
            f"{field_name} must be {expected.__name__}",
            details={
                "reason_code": "invalid_experiment_field_type",
                "field": field_name,
            },
        )


_FAILURE_OUTCOMES = frozenset(
    {ExperimentStatus.COMPLETED_WITH_FAILURES, ExperimentStatus.FAILED}
)


def _validate_failure_code(
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
    *,
    allowed_statuses: frozenset[ExperimentStatus],
) -> None:
    if failure_code is not None:
        _require_instance(failure_code, ExperimentFailureCode, "failure_code")
        if status not in allowed_statuses:
            raise ExperimentSpecError(
                "failure_code is only valid for failed outcomes",
                details={"reason_code": "failure_code_without_failure_outcome"},
            )
    if status in _FAILURE_OUTCOMES and failure_code is None:
        raise ExperimentSpecError(
            "failure outcomes require a stable failure_code",
            details={"reason_code": "failure_code_required"},
        )


def _validate_attempt_lineage(
    attempt_id: AttemptId,
    ordinal: int,
    parent_attempt_id: AttemptId | None,
) -> None:
    if parent_attempt_id is not None:
        _require_instance(parent_attempt_id, AttemptId, "parent_attempt_id")
        if parent_attempt_id == attempt_id:
            raise ExperimentSpecError(
                "retry attempt cannot be its own parent",
                details={"reason_code": "invalid_attempt_lineage"},
            )
    if ordinal > 1 and parent_attempt_id is None:
        raise ExperimentSpecError(
            "retry attempt must reference its immutable parent attempt",
            details={"reason_code": "invalid_attempt_lineage"},
        )
    if ordinal == 1 and parent_attempt_id is not None:
        raise ExperimentSpecError(
            "first attempt cannot reference a parent attempt",
            details={"reason_code": "invalid_attempt_lineage"},
        )


def _validate_attempt_references(
    resume_from_run_id: BacktestRunId | None,
    checkpoint_ref: CheckpointRef | None,
) -> None:
    if resume_from_run_id is not None:
        _require_instance(
            resume_from_run_id,
            BacktestRunId,
            "resume_from_run_id",
        )
    if checkpoint_ref is not None:
        _require_instance(checkpoint_ref, CheckpointRef, "checkpoint_ref")


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    """Immutable projection of an experiment's observed control state."""

    experiment_id: ExperimentId
    status: ExperimentStatus
    desired_state: ExperimentDesiredState
    stage: ExperimentStage
    created_at: datetime
    failure_code: ExperimentFailureCode | None = None

    def __post_init__(self) -> None:
        """Validate identity, enum separation, timestamp, and failure semantics."""
        _require_instance(self.experiment_id, ExperimentId, "experiment_id")
        _require_instance(self.status, ExperimentStatus, "status")
        _require_instance(self.desired_state, ExperimentDesiredState, "desired_state")
        _require_instance(self.stage, ExperimentStage, "stage")
        _require_utc(self.created_at, "created_at")
        _validate_failure_code(
            self.status,
            self.failure_code,
            allowed_statuses=_FAILURE_OUTCOMES | {ExperimentStatus.BLOCKED},
        )


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    """Stable candidate identity within one experiment."""

    candidate_id: CandidateId
    experiment_id: ExperimentId
    ordinal: int
    is_baseline: bool = False

    def __post_init__(self) -> None:
        """Validate candidate identity and stable ordinal."""
        _require_instance(self.candidate_id, CandidateId, "candidate_id")
        _require_instance(self.experiment_id, ExperimentId, "experiment_id")
        _require_positive_ordinal(self.ordinal, "candidate_ordinal")
        if type(self.is_baseline) is not bool:
            raise ExperimentSpecError(
                "is_baseline must be bool",
                details={"reason_code": "invalid_baseline_marker"},
            )


@dataclass(frozen=True, slots=True)
class FoldRecord:
    """Stable fold identity and its experiment/candidate parents."""

    fold_id: FoldId
    experiment_id: ExperimentId
    candidate_id: CandidateId
    ordinal: int

    def __post_init__(self) -> None:
        """Validate fold identity, parents, and ordinal."""
        _require_instance(self.fold_id, FoldId, "fold_id")
        _require_instance(self.experiment_id, ExperimentId, "experiment_id")
        _require_instance(self.candidate_id, CandidateId, "candidate_id")
        _require_positive_ordinal(self.ordinal, "fold_ordinal")


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Immutable execution attempt; retries append instead of overwriting."""

    attempt_id: AttemptId
    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId
    ordinal: int
    status: ExperimentStatus
    created_at: datetime
    parent_attempt_id: AttemptId | None = None
    resume_from_run_id: BacktestRunId | None = None
    checkpoint_ref: CheckpointRef | None = None
    failure_code: ExperimentFailureCode | None = None

    def __post_init__(self) -> None:
        """Validate attempt identity, lineage, and opaque references."""
        _require_instance(self.attempt_id, AttemptId, "attempt_id")
        _require_instance(self.experiment_id, ExperimentId, "experiment_id")
        _require_instance(self.candidate_id, CandidateId, "candidate_id")
        _require_instance(self.fold_id, FoldId, "fold_id")
        _require_positive_ordinal(self.ordinal, "attempt_ordinal")
        _require_instance(self.status, ExperimentStatus, "status")
        _require_utc(self.created_at, "created_at")
        if self.status in {ExperimentStatus.DRAFT, ExperimentStatus.BLOCKED}:
            raise ExperimentSpecError(
                "attempt records cannot use pre-attempt experiment statuses",
                details={"reason_code": "invalid_attempt_status"},
            )
        _validate_attempt_lineage(
            self.attempt_id,
            self.ordinal,
            self.parent_attempt_id,
        )
        _validate_attempt_references(
            self.resume_from_run_id,
            self.checkpoint_ref,
        )
        _validate_failure_code(
            self.status,
            self.failure_code,
            allowed_statuses=_FAILURE_OUTCOMES,
        )


_LEGAL_STATUS_TRANSITIONS: dict[ExperimentStatus, frozenset[ExperimentStatus]] = {
    ExperimentStatus.DRAFT: frozenset(
        {ExperimentStatus.BLOCKED, ExperimentStatus.QUEUED}
    ),
    ExperimentStatus.BLOCKED: frozenset(),
    ExperimentStatus.QUEUED: frozenset(
        {ExperimentStatus.RUNNING, ExperimentStatus.CANCEL_REQUESTED}
    ),
    ExperimentStatus.RUNNING: frozenset(
        {
            ExperimentStatus.PAUSE_REQUESTED,
            ExperimentStatus.CANCEL_REQUESTED,
            ExperimentStatus.COMPLETED,
            ExperimentStatus.COMPLETED_WITH_FAILURES,
            ExperimentStatus.FAILED,
        }
    ),
    ExperimentStatus.PAUSE_REQUESTED: frozenset({ExperimentStatus.PAUSED}),
    ExperimentStatus.PAUSED: frozenset(
        {ExperimentStatus.QUEUED, ExperimentStatus.CANCEL_REQUESTED}
    ),
    ExperimentStatus.CANCEL_REQUESTED: frozenset({ExperimentStatus.CANCELLED}),
    ExperimentStatus.CANCELLED: frozenset(),
    ExperimentStatus.COMPLETED: frozenset(),
    ExperimentStatus.COMPLETED_WITH_FAILURES: frozenset(),
    ExperimentStatus.FAILED: frozenset(),
}


def validate_status_transition(
    current: ExperimentStatus,
    target: ExperimentStatus,
    *,
    attempt_started: bool,
    precondition_repairable: bool = False,
) -> ExperimentStatus:
    """Fail closed unless an observed status transition satisfies all invariants."""
    raw_current = cast("object", current)
    raw_target = cast("object", target)
    if not isinstance(raw_current, ExperimentStatus) or not isinstance(
        raw_target, ExperimentStatus
    ):
        raise ExperimentStateTransitionError(
            "unknown experiment status",
            details={"reason_code": "unknown_experiment_status"},
        )
    if type(attempt_started) is not bool or type(precondition_repairable) is not bool:
        raise ExperimentStateTransitionError(
            "transition context flags must be bool",
            details={"reason_code": "invalid_transition_context"},
        )
    current = raw_current
    target = raw_target
    if target not in _LEGAL_STATUS_TRANSITIONS[current]:
        raise ExperimentStateTransitionError(
            f"illegal experiment transition: {current.value} -> {target.value}",
            details={
                "reason_code": "illegal_experiment_state_transition",
                "current_status": current.value,
                "target_status": target.value,
            },
        )
    if target is ExperimentStatus.BLOCKED and (
        attempt_started or not precondition_repairable
    ):
        raise ExperimentStateTransitionError(
            "blocked requires a repairable preflight condition before any attempt",
            details={
                "reason_code": "invalid_blocked_transition",
                "current_status": current.value,
                "target_status": target.value,
            },
        )
    if target is ExperimentStatus.FAILED and not attempt_started:
        raise ExperimentStateTransitionError(
            "failed requires an attempt that has started",
            details={
                "reason_code": "invalid_failed_transition",
                "current_status": current.value,
                "target_status": target.value,
            },
        )
    return target
