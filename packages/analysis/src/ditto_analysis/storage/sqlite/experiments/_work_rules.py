"""Lifecycle and SQL-aware liveness guards for fenced experiment work."""

from __future__ import annotations

import sqlite3

from ditto_analysis.errors import ExperimentIntegrityError, ExperimentSpecError
from ditto_analysis.experiments.models import (
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import FoldKey
from ditto_analysis.storage.sqlite.experiments._experiment_rules import (
    TERMINAL_EXPERIMENT_STATUSES,
)

_FOLD_TRANSITIONS = frozenset(
    {
        (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING),
        (ExperimentStatus.QUEUED, ExperimentStatus.CANCELLED),
        (ExperimentStatus.RUNNING, ExperimentStatus.QUEUED),
        (ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED),
        (ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED),
        (ExperimentStatus.RUNNING, ExperimentStatus.FAILED),
    }
)
_ATTEMPT_TRANSITIONS = frozenset(
    {
        (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING),
        (ExperimentStatus.QUEUED, ExperimentStatus.CANCELLED),
        (ExperimentStatus.RUNNING, ExperimentStatus.RUNNING),
        (ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED),
        (ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED),
        (ExperimentStatus.RUNNING, ExperimentStatus.FAILED),
    }
)
_RETRYABLE_TERMINAL_FAILURE_CODES = frozenset(
    {
        ExperimentFailureCode.LEASE_LOST,
        ExperimentFailureCode.SYSTEM_ERROR,
    }
)


def find_experiment_live_child(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
    target_status: ExperimentStatus,
) -> dict[str, str] | None:
    """Return the first child that prevents a paused or terminal projection."""
    if (
        target_status is not ExperimentStatus.PAUSED
        and target_status not in TERMINAL_EXPERIMENT_STATUSES
    ):
        return None
    attempt = connection.execute(
        """
        SELECT attempt_id, status FROM experiment_attempt
        WHERE experiment_id=? AND status IN ('queued', 'running')
        ORDER BY candidate_id, fold_id, ordinal, attempt_id
        LIMIT 1
        """,
        (str(experiment_id),),
    ).fetchone()
    if attempt is not None:
        return {
            "target_status": target_status.value,
            "child_type": "attempt",
            "child_status": attempt["status"],
            "attempt_id": attempt["attempt_id"],
        }
    if target_status is ExperimentStatus.PAUSED:
        fold = connection.execute(
            """
            SELECT candidate_id, fold_id, status FROM experiment_fold
            WHERE experiment_id=? AND status='running'
            ORDER BY candidate_id, ordinal, fold_id
            LIMIT 1
            """,
            (str(experiment_id),),
        ).fetchone()
    else:
        fold = connection.execute(
            """
            SELECT candidate_id, fold_id, status FROM experiment_fold
            WHERE experiment_id=? AND status IN ('queued', 'running')
            ORDER BY candidate_id, ordinal, fold_id
            LIMIT 1
            """,
            (str(experiment_id),),
        ).fetchone()
    if fold is None:
        return None
    return {
        "target_status": target_status.value,
        "child_type": "fold",
        "child_status": fold["status"],
        "candidate_id": fold["candidate_id"],
        "fold_id": fold["fold_id"],
    }


def validate_experiment_dispatchable(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
) -> None:
    """Require active RUN intent before starting any new fold work."""
    row = connection.execute(
        "SELECT status, desired_state FROM experiment WHERE experiment_id=?",
        (str(experiment_id),),
    ).fetchone()
    if row is None:
        raise ExperimentIntegrityError(
            "fold parent experiment does not exist",
            details={"reason_code": "experiment_not_found"},
        )
    if (
        row["status"] != ExperimentStatus.RUNNING.value
        or row["desired_state"] != ExperimentDesiredState.RUN.value
    ):
        raise ExperimentSpecError(
            "experiment lifecycle does not permit new fold dispatch",
            details={
                "reason_code": "experiment_not_dispatchable",
                "status": row["status"],
                "desired_state": row["desired_state"],
            },
        )


def validate_new_fold_creation_allowed(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
) -> None:
    """Require the draft construction phase before inserting a new fold."""
    row = connection.execute(
        "SELECT status, desired_state FROM experiment WHERE experiment_id=?",
        (str(experiment_id),),
    ).fetchone()
    if row is None:
        raise ExperimentIntegrityError(
            "fold parent experiment does not exist",
            details={"reason_code": "experiment_not_found"},
        )
    if (
        row["status"] != ExperimentStatus.DRAFT.value
        or row["desired_state"] != ExperimentDesiredState.RUN.value
    ):
        raise ExperimentSpecError(
            "new folds can be added only while the experiment is draft with run intent",
            details={
                "reason_code": "fold_creation_not_allowed",
                "status": row["status"],
                "desired_state": row["desired_state"],
            },
        )


def validate_attempt_start_dispatchable(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
    previous: ExperimentStatus,
    target: ExperimentStatus,
) -> None:
    """Fence only a queued attempt's first transition into active work."""
    if previous is ExperimentStatus.QUEUED and target is ExperimentStatus.RUNNING:
        validate_experiment_dispatchable(connection, experiment_id)


def validate_terminal_fold_retry_experiment(
    *,
    experiment_status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
) -> None:
    """Require active RUN intent before retrying terminal fold work."""
    if (
        experiment_status is not ExperimentStatus.RUNNING
        or desired_state is not ExperimentDesiredState.RUN
    ):
        raise ExperimentSpecError(
            "terminal fold retry requires a running experiment with run intent",
            details={
                "reason_code": "terminal_fold_retry_experiment_not_running",
                "status": experiment_status.value,
                "desired_state": desired_state.value,
            },
        )


def validate_terminal_fold_retry_target(
    *,
    fold_status: ExperimentStatus,
    fold_failure_code: ExperimentFailureCode | None,
) -> None:
    """Require a retryable failed fold outcome."""
    if fold_status is not ExperimentStatus.FAILED:
        raise ExperimentSpecError(
            "terminal fold retry requires a failed fold",
            details={
                "reason_code": "terminal_fold_retry_requires_failed_fold",
                "status": fold_status.value,
            },
        )
    if fold_failure_code not in _RETRYABLE_TERMINAL_FAILURE_CODES:
        raise ExperimentSpecError(
            "terminal fold failure is not retryable",
            details={
                "reason_code": "terminal_fold_retry_failure_not_retryable",
                "failure_code": (
                    None if fold_failure_code is None else fold_failure_code.value
                ),
            },
        )


def validate_terminal_fold_retry_parent(
    *,
    parent_status: ExperimentStatus,
    parent_failure_code: ExperimentFailureCode | None,
    fold_failure_code: ExperimentFailureCode,
) -> None:
    """Require a matching system/lease terminal outcome on the latest attempt."""
    if (
        parent_status is not ExperimentStatus.FAILED
        or parent_failure_code is None
        or parent_failure_code not in _RETRYABLE_TERMINAL_FAILURE_CODES
    ):
        raise ExperimentSpecError(
            "terminal fold retry parent attempt is not retryable",
            details={
                "reason_code": "terminal_fold_retry_parent_not_retryable",
                "status": parent_status.value,
                "failure_code": (
                    None if parent_failure_code is None else parent_failure_code.value
                ),
            },
        )
    if parent_failure_code is not fold_failure_code:
        raise ExperimentIntegrityError(
            "terminal fold and parent attempt failure lineage differs",
            details={
                "reason_code": "terminal_fold_retry_failure_lineage_mismatch",
                "fold_failure_code": fold_failure_code.value,
                "parent_failure_code": parent_failure_code.value,
            },
        )


def validate_fold_transition(
    previous: ExperimentStatus,
    target: ExperimentStatus,
    *,
    claim_owner_token: str | None,
    fence_owner_token: str,
    failure_code: ExperimentFailureCode | None,
    reason_code: str | None,
) -> None:
    """Reject illegal fold edges and ambiguous recovery transitions."""
    if (previous, target) not in _FOLD_TRANSITIONS:
        raise ExperimentSpecError(
            f"invalid fold transition: {previous.value} -> {target.value}",
            details={"reason_code": "invalid_fold_transition"},
        )
    if target is ExperimentStatus.RUNNING:
        if claim_owner_token != fence_owner_token:
            raise ExperimentSpecError(
                "running fold must be owned by the current lease owner",
                details={"reason_code": "invalid_fold_claim_owner"},
            )
    elif claim_owner_token is not None:
        raise ExperimentSpecError(
            "non-running fold cannot retain a claim owner",
            details={"reason_code": "invalid_fold_claim_owner"},
        )
    if (
        previous is ExperimentStatus.RUNNING
        and target is ExperimentStatus.QUEUED
        and reason_code not in {"crash_recovery", "pause_recovery_requeue"}
    ):
        raise ExperimentSpecError(
            "running fold can requeue only through an atomic recovery command",
            details={"reason_code": "crash_recovery_reason_required"},
        )
    if (target is ExperimentStatus.FAILED) != (failure_code is not None):
        raise ExperimentSpecError(
            "fold failure code must exactly match a failed outcome",
            details={"reason_code": "invalid_fold_failure_code"},
        )


def validate_attempt_transition(
    previous: ExperimentStatus,
    target: ExperimentStatus,
) -> None:
    """Allow only queued dispatch, running checkpoints, and terminal completion."""
    if (previous, target) not in _ATTEMPT_TRANSITIONS:
        raise ExperimentSpecError(
            f"invalid attempt transition: {previous.value} -> {target.value}",
            details={"reason_code": "invalid_attempt_transition"},
        )


def validate_attempt_fold_owner(
    connection: sqlite3.Connection,
    key: FoldKey,
    owner_token: str,
) -> None:
    """Require attempt creation under the currently claimed parent fold."""
    row = connection.execute(
        """
        SELECT status, claim_owner_token FROM experiment_fold
        WHERE experiment_id=? AND candidate_id=? AND fold_id=?
        """,
        (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
    ).fetchone()
    if row is None:
        raise ExperimentIntegrityError(
            "attempt parent fold does not exist",
            details={"reason_code": "attempt_fold_not_found"},
        )
    if (
        row["status"] != ExperimentStatus.RUNNING.value
        or row["claim_owner_token"] != owner_token
    ):
        raise ExperimentIntegrityError(
            "attempt parent fold is not owned by the lease worker",
            details={"reason_code": "attempt_fold_not_claimed"},
        )
