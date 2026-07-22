"""Full persisted-history validation for exact holdout claim replay."""

from __future__ import annotations

import sqlite3
from collections import Counter

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments._time import epoch_us
from ditto_analysis.experiments.models import ExperimentStatus
from ditto_analysis.experiments.persistence import HoldoutClaimRecord
from ditto_analysis.storage.sqlite.experiments._events import (
    canonical_status_event_id,
    event_values,
)
from ditto_analysis.storage.sqlite.experiments._holdout_isolation import (
    validate_candidate_isolated_holdout,
)


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


def validate_holdout_replay_history(
    connection: sqlite3.Connection,
    record: HoldoutClaimRecord,
) -> None:
    """Require every frozen candidate and unselected cancellation to remain exact."""
    candidate_rows = connection.execute(
        """
        SELECT candidate_id FROM experiment_candidate
        WHERE experiment_id=? ORDER BY candidate_id
        """,
        (str(record.fold_key.experiment_id),),
    ).fetchall()
    fold_rows = connection.execute(
        """
        SELECT * FROM experiment_fold
        WHERE experiment_id=? AND fold_role='holdout'
        ORDER BY candidate_id, ordinal, fold_id
        """,
        (str(record.fold_key.experiment_id),),
    ).fetchall()
    expected = Counter(row["candidate_id"] for row in candidate_rows)
    observed = Counter(row["candidate_id"] for row in fold_rows)
    if not expected or observed != expected:
        raise _integrity(
            "holdout fold cardinality differs from frozen candidates",
            "holdout_fold_cardinality_drift",
        )
    unselected = tuple(
        row
        for row in fold_rows
        if row["candidate_id"] != str(record.fold_key.candidate_id)
        or row["fold_id"] != str(record.fold_key.fold_id)
    )
    for fold in unselected:
        if (
            fold["status"] != ExperimentStatus.CANCELLED.value
            or fold["claim_owner_token"] is not None
        ):
            raise _integrity(
                "unselected holdout fold is not durably cancelled",
                "holdout_unselected_fold_drift",
            )
        event_id = canonical_status_event_id(
            subject_type="fold",
            experiment_id=fold["experiment_id"],
            candidate_id=fold["candidate_id"],
            fold_id=fold["fold_id"],
            attempt_id=None,
            revision=fold["revision"],
        )
        event = connection.execute(
            "SELECT * FROM experiment_status_event WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if event is not None and event["reason_code"] == (
            "candidate_isolated_after_failure"
        ):
            validate_candidate_isolated_holdout(connection, fold)
            continue
        expected_event = event_values(
            subject_type="fold",
            experiment_id=fold["experiment_id"],
            candidate_id=fold["candidate_id"],
            fold_id=fold["fold_id"],
            attempt_id=None,
            revision=fold["revision"],
            previous_status=ExperimentStatus.QUEUED,
            status=ExperimentStatus.CANCELLED,
            desired_state=None,
            stage=None,
            failure_code=None,
            reason_code="holdout_candidate_not_selected",
            detail={
                "claim_id": record.claim_id,
                "selected_candidate_id": str(record.fold_key.candidate_id),
            },
            occurred_at_epoch_us=epoch_us(record.claimed_at),
        )
        if event is None or tuple(event) != expected_event:
            raise _integrity(
                "unselected holdout cancellation event is missing or drifted",
                "holdout_unselected_event_drift",
            )
