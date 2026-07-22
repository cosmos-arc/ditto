"""Fail-closed holdout claim checks shared by dispatch and retry paths."""

from __future__ import annotations

import sqlite3

from ditto_analysis.errors import ExperimentIntegrityError, ExperimentSpecError
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
)
from ditto_analysis.experiments.persistence import FoldKey


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


def validate_holdout_work_authority(
    connection: sqlite3.Connection,
    key: FoldKey,
    reproduction_fingerprint: ContentHash,
) -> None:
    """Require exact claim lineage before any sealed-holdout work mutation."""
    fold = connection.execute(
        """
        SELECT fold_role FROM experiment_fold
        WHERE experiment_id=? AND candidate_id=? AND fold_id=?
        """,
        (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
    ).fetchone()
    if fold is None:
        raise _integrity("fold does not exist", "fold_not_found")
    if fold["fold_role"] != "holdout":
        return
    experiment = connection.execute(
        "SELECT stage FROM experiment WHERE experiment_id=?",
        (str(key.experiment_id),),
    ).fetchone()
    claims = connection.execute(
        "SELECT * FROM holdout_claim WHERE experiment_id=? ORDER BY claim_id",
        (str(key.experiment_id),),
    ).fetchall()
    if experiment is None or experiment["stage"] not in {
        ExperimentStage.HOLDOUT.value,
        ExperimentStage.EVIDENCE.value,
    }:
        raise ExperimentSpecError(
            "holdout work requires the claimed experiment stage",
            details={"reason_code": "holdout_claim_required"},
        )
    if len(claims) != 1:
        raise _integrity(
            "holdout work requires one unambiguous claim",
            "holdout_claim_missing_or_ambiguous",
        )
    claim = claims[0]
    if claim["candidate_id"] != str(key.candidate_id) or claim["fold_id"] != str(
        key.fold_id
    ):
        raise ExperimentSpecError(
            "holdout work is not the selected claim fold",
            details={"reason_code": "holdout_claim_fold_mismatch"},
        )
    if claim["reproduction_fingerprint"] != str(reproduction_fingerprint):
        raise ExperimentSpecError(
            "holdout work fingerprint differs from the immutable claim",
            details={"reason_code": "holdout_claim_fingerprint_mismatch"},
        )


def reject_unbound_holdout_dispatch(
    fold: sqlite3.Row,
    target_status: ExperimentStatus,
) -> None:
    """Reject the legacy claim-fold path because it has no fingerprint input."""
    if target_status is ExperimentStatus.RUNNING and fold["fold_role"] == "holdout":
        raise ExperimentSpecError(
            "holdout dispatch requires an atomic fingerprint-bound claim",
            details={"reason_code": "holdout_atomic_dispatch_required"},
        )


def validate_holdout_attempt_row(
    connection: sqlite3.Connection,
    attempt: sqlite3.Row,
) -> None:
    """Recheck persisted claim authority before attempt state mutation."""
    validate_holdout_work_authority(
        connection,
        FoldKey(
            ExperimentId(attempt["experiment_id"]),
            CandidateId(attempt["candidate_id"]),
            FoldId(attempt["fold_id"]),
        ),
        ContentHash(attempt["reproduction_fingerprint"]),
    )
