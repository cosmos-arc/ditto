"""Pure lifecycle guards for fenced fold and attempt work items."""

from __future__ import annotations

import sqlite3

from ditto_analysis.errors import ExperimentIntegrityError, ExperimentSpecError
from ditto_analysis.experiments.models import ExperimentFailureCode, ExperimentStatus
from ditto_analysis.experiments.persistence import FoldKey

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


def validate_fold_transition(
    previous: ExperimentStatus,
    target: ExperimentStatus,
    *,
    claim_owner_token: str | None,
    fence_owner_token: str,
    failure_code: ExperimentFailureCode | None,
    reason_code: str | None,
) -> None:
    """Reject illegal fold edges and ambiguous crash recovery."""
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
        and reason_code != "crash_recovery"
    ):
        raise ExperimentSpecError(
            "running fold can requeue only for crash recovery",
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
