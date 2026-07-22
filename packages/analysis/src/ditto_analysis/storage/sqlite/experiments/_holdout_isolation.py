"""Canonical provenance for holdout folds cancelled by candidate isolation."""

from __future__ import annotations

import sqlite3

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments.models import (
    ExperimentFailureCode,
    ExperimentStatus,
)
from ditto_analysis.storage.sqlite.experiments._events import event_values


def _integrity(message: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": "holdout_candidate_isolation_drift"},
    )


def _exact_event(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    subject_type: str,
    previous_status: ExperimentStatus,
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
    reason_code: str,
) -> bool:
    attempt_id = row["attempt_id"] if subject_type == "attempt" else None
    event = connection.execute(
        """
        SELECT * FROM experiment_status_event
        WHERE experiment_id=? AND candidate_id=? AND fold_id=?
          AND attempt_id IS ? AND subject_type=? AND subject_revision=?
        """,
        (
            row["experiment_id"],
            row["candidate_id"],
            row["fold_id"],
            attempt_id,
            subject_type,
            row["revision"],
        ),
    ).fetchone()
    expected = event_values(
        subject_type=subject_type,
        experiment_id=row["experiment_id"],
        candidate_id=row["candidate_id"],
        fold_id=row["fold_id"],
        attempt_id=attempt_id,
        revision=row["revision"],
        previous_status=previous_status,
        status=status,
        desired_state=None,
        stage=None,
        failure_code=failure_code,
        reason_code=reason_code,
        detail={},
        occurred_at_epoch_us=row["updated_at_epoch_us"],
    )
    return event is not None and tuple(event) == expected


def validate_candidate_isolated_holdout(
    connection: sqlite3.Connection,
    fold: sqlite3.Row,
) -> None:
    """Require exact cancellation plus durable candidate-failure provenance."""
    if (
        fold["fold_role"] != "holdout"
        or fold["status"] != ExperimentStatus.CANCELLED.value
        or fold["claim_owner_token"] is not None
        or not _exact_event(
            connection,
            fold,
            subject_type="fold",
            previous_status=ExperimentStatus.QUEUED,
            status=ExperimentStatus.CANCELLED,
            failure_code=None,
            reason_code="candidate_isolated_after_failure",
        )
    ):
        raise _integrity("isolated holdout cancellation event is invalid")
    failed_attempts = connection.execute(
        """
        SELECT * FROM experiment_attempt
        WHERE experiment_id=? AND candidate_id=? AND status='failed'
          AND failure_code='candidate_failed'
        ORDER BY attempt_id
        """,
        (fold["experiment_id"], fold["candidate_id"]),
    ).fetchall()
    failed_folds = connection.execute(
        """
        SELECT * FROM experiment_fold
        WHERE experiment_id=? AND candidate_id=? AND status='failed'
        ORDER BY fold_id
        """,
        (fold["experiment_id"], fold["candidate_id"]),
    ).fetchall()
    exact_attempts = tuple(
        row
        for row in failed_attempts
        if _exact_event(
            connection,
            row,
            subject_type="attempt",
            previous_status=ExperimentStatus.RUNNING,
            status=ExperimentStatus.FAILED,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
            reason_code="candidate_attempt_failed",
        )
    )
    exact_folds = tuple(
        row
        for row in failed_folds
        if _exact_event(
            connection,
            row,
            subject_type="fold",
            previous_status=ExperimentStatus.RUNNING,
            status=ExperimentStatus.FAILED,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
            reason_code="candidate_fold_failed",
        )
    )
    if (
        not exact_attempts
        or not exact_folds
        or not any(
            attempt["fold_id"] == failed_fold["fold_id"]
            for attempt in exact_attempts
            for failed_fold in exact_folds
        )
    ):
        raise _integrity("candidate failure provenance is missing or drifted")
