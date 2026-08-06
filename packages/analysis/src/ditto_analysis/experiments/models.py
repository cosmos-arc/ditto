"""Pure experiment control-plane identities, states, and records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import (
    ExperimentIdentityError,
    ExperimentSpecError,
    ExperimentStateTransitionError,
)
from ditto_analysis.experiments._validation import require_utc_datetime

__all__ = [
    "AttemptId",
    "BacktestRunId",
    "CandidateId",
    "CheckpointRef",
    "ContentHash",
    "ExperimentDesiredState",
    "ExperimentFailureCode",
    "ExperimentId",
    "ExperimentRecord",
    "ExperimentStage",
    "ExperimentStatus",
    "FoldId",
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

    SNAPSHOT_NOT_CERTIFIED = "snapshot_not_certified"
    INSUFFICIENT_HISTORY = "insufficient_history"
    CANDIDATE_FAILED = "candidate_failed"
    INPUT_HASH_MISMATCH = "input_hash_mismatch"
    LEASE_LOST = "lease_lost"
    SYSTEM_ERROR = "system_error"


def _require_instance(value: object, expected: type, field_name: str) -> None:
    if not isinstance(value, expected):
        raise ExperimentSpecError(
            f"{field_name} must be {expected.__name__}",
            details={
                "reason_code": "invalid_experiment_field_type",
                "field": field_name,
            },
        )


@dataclass(frozen=True, slots=True)
class _FailureCodePolicy:
    """Allowed codes and presence rule for one record status."""

    required: bool
    allowed_codes: frozenset[ExperimentFailureCode]


_NO_FAILURE_CODE = _FailureCodePolicy(required=False, allowed_codes=frozenset())
_BLOCKER_CODES = frozenset(
    {
        ExperimentFailureCode.SNAPSHOT_NOT_CERTIFIED,
        ExperimentFailureCode.INSUFFICIENT_HISTORY,
    }
)
_LOCAL_FAILURE_CODES = frozenset({ExperimentFailureCode.CANDIDATE_FAILED})
_HARD_FAILURE_CODES = frozenset(
    {
        ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ExperimentFailureCode.LEASE_LOST,
        ExperimentFailureCode.SYSTEM_ERROR,
    }
)
_EXPERIMENT_FAILURE_CODE_POLICY = {
    ExperimentStatus.DRAFT: _NO_FAILURE_CODE,
    ExperimentStatus.BLOCKED: _FailureCodePolicy(
        required=False,
        allowed_codes=_BLOCKER_CODES,
    ),
    ExperimentStatus.QUEUED: _NO_FAILURE_CODE,
    ExperimentStatus.RUNNING: _NO_FAILURE_CODE,
    ExperimentStatus.PAUSE_REQUESTED: _NO_FAILURE_CODE,
    ExperimentStatus.PAUSED: _NO_FAILURE_CODE,
    ExperimentStatus.CANCEL_REQUESTED: _NO_FAILURE_CODE,
    ExperimentStatus.CANCELLED: _NO_FAILURE_CODE,
    ExperimentStatus.COMPLETED: _NO_FAILURE_CODE,
    ExperimentStatus.COMPLETED_WITH_FAILURES: _FailureCodePolicy(
        required=True,
        allowed_codes=_LOCAL_FAILURE_CODES,
    ),
    ExperimentStatus.FAILED: _FailureCodePolicy(
        required=True,
        allowed_codes=_HARD_FAILURE_CODES,
    ),
}


def _validate_failure_code(
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
    *,
    policy_by_status: dict[ExperimentStatus, _FailureCodePolicy],
) -> None:
    policy = policy_by_status.get(status)
    if policy is None:
        raise ExperimentSpecError(
            f"no failure-code policy exists for status '{status.value}'",
            details={
                "reason_code": "invalid_failure_policy_status",
                "status": status.value,
            },
        )
    if failure_code is None:
        if not policy.required:
            return
        raise ExperimentSpecError(
            f"status '{status.value}' requires a stable failure_code",
            details={
                "reason_code": "failure_code_required",
                "status": status.value,
            },
        )
    _require_instance(failure_code, ExperimentFailureCode, "failure_code")
    if failure_code in policy.allowed_codes:
        return
    if not policy.allowed_codes:
        raise ExperimentSpecError(
            f"status '{status.value}' does not accept failure_code",
            details={
                "reason_code": "failure_code_without_failure_outcome",
                "status": status.value,
                "failure_code": failure_code.value,
            },
        )
    raise ExperimentSpecError(
        f"failure_code '{failure_code.value}' is not valid for status '{status.value}'",
        details={
            "reason_code": "failure_code_not_allowed_for_status",
            "status": status.value,
            "failure_code": failure_code.value,
        },
    )


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
        require_utc_datetime(self.created_at, "created_at")
        _validate_failure_code(
            self.status,
            self.failure_code,
            policy_by_status=_EXPERIMENT_FAILURE_CODE_POLICY,
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
