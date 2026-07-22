"""Atomic fenced dispatch of a fold and its first attempt."""

# Approved typed command surfaces intentionally carry explicit fencing/event fields.
# ruff: noqa: PLR0913

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
    AttemptId,
    BacktestRunId,
    CheckpointRef,
    ContentHash,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import (
    AttemptPersistenceSpec,
    AttemptProjection,
    FoldKey,
    FoldProjection,
    LeaseFence,
)
from ditto_analysis.storage.sqlite.experiments._holdout_authority import (
    validate_holdout_work_authority,
)
from ditto_analysis.storage.sqlite.experiments._work_rules import (
    validate_attempt_fold_owner,
    validate_experiment_dispatchable,
    validate_fold_transition,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)


def _epoch_us(value: datetime) -> int:
    require_utc_datetime(value, "datetime")
    return int(value.timestamp() * 1_000_000)


def _optional(value: object | None) -> str | None:
    return None if value is None else str(value)


def _conflict(message: str, reason_code: str) -> ExperimentConflictError:
    return ExperimentConflictError(message, details={"reason_code": reason_code})


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


class SQLiteAtomicDispatchMixin:
    """Claim one queued fold and create its first attempt in one transaction."""

    _database: ResearchExperimentDatabase

    @classmethod
    def _validate_lease(
        cls,
        connection: sqlite3.Connection,
        fence: LeaseFence,
        now_epoch_us: int,
        expected_experiment_id: ExperimentId,
    ) -> sqlite3.Row: ...

    @staticmethod
    def _validate_initial_attempt(
        spec: AttemptPersistenceSpec, initial: AttemptProjection
    ) -> None: ...

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        subject_type: str,
        experiment_id: str,
        candidate_id: str | None,
        fold_id: str | None,
        attempt_id: str | None,
        revision: int,
        previous_status: ExperimentStatus | None,
        status: ExperimentStatus,
        desired_state: ExperimentDesiredState | None,
        stage: ExperimentStage | None,
        failure_code: ExperimentFailureCode | None,
        reason_code: str | None,
        detail: Mapping[str, object],
        occurred_at: datetime,
    ) -> None: ...

    def claim_fold_and_add_attempt(
        self,
        key: FoldKey,
        spec: AttemptPersistenceSpec,
        initial: AttemptProjection,
        *,
        expected_fold_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldProjection, AttemptProjection]:
        self._validate_initial_attempt(spec, initial)
        if spec.fold_key != key:
            raise ExperimentSpecError(
                "atomic dispatch attempt must belong to the claimed fold",
                details={"reason_code": "atomic_dispatch_lineage_mismatch"},
            )
        if spec.ordinal == 1 and spec.resume_from_run_id is not None:
            raise ExperimentSpecError(
                "first attempt cannot resume a prior backtest run",
                details={"reason_code": "first_attempt_cannot_resume"},
            )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(
                connection, lease_fence, now_epoch_us, key.experiment_id
            )
            validate_experiment_dispatchable(connection, key.experiment_id)
            fold = connection.execute(
                """
                SELECT * FROM experiment_fold
                WHERE experiment_id=? AND candidate_id=? AND fold_id=?
                """,
                (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
            ).fetchone()
            if fold is None:
                raise _integrity("fold does not exist", "fold_not_found")
            if fold["revision"] != expected_fold_revision:
                raise _conflict("fold revision is stale", "stale_projection_revision")
            validate_holdout_work_authority(
                connection,
                key,
                spec.reproduction_fingerprint,
            )
            self._validate_dispatch_attempt_lineage(connection, key, spec)
            previous_status = ExperimentStatus(fold["status"])
            validate_fold_transition(
                previous_status,
                ExperimentStatus.RUNNING,
                claim_owner_token=lease_fence.owner_token,
                fence_owner_token=lease_fence.owner_token,
                failure_code=None,
                reason_code="fold_claimed",
            )
            new_fold_revision = expected_fold_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_fold
                SET status='running', claim_owner_token=?, updated_at_epoch_us=?,
                    revision=?
                WHERE experiment_id=? AND candidate_id=? AND fold_id=? AND revision=?
                """,
                (
                    lease_fence.owner_token,
                    _epoch_us(occurred_at),
                    new_fold_revision,
                    str(key.experiment_id),
                    str(key.candidate_id),
                    str(key.fold_id),
                    expected_fold_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("fold CAS lost", "stale_projection_revision")
            self._insert_event(
                connection,
                subject_type="fold",
                experiment_id=str(key.experiment_id),
                candidate_id=str(key.candidate_id),
                fold_id=str(key.fold_id),
                attempt_id=None,
                revision=new_fold_revision,
                previous_status=previous_status,
                status=ExperimentStatus.RUNNING,
                desired_state=None,
                stage=None,
                failure_code=None,
                reason_code="fold_claimed",
                detail={},
                occurred_at=occurred_at,
            )
            validate_attempt_fold_owner(connection, key, lease_fence.owner_token)
            values = (
                str(spec.attempt_id),
                str(key.experiment_id),
                str(key.candidate_id),
                str(key.fold_id),
                spec.ordinal,
                _optional(spec.parent_attempt_id),
                initial.status.value,
                _optional(initial.backtest_run_id),
                _optional(spec.resume_from_run_id),
                _optional(initial.checkpoint_ref),
                str(spec.reproduction_fingerprint),
                _optional(initial.failure_code),
                _epoch_us(spec.created_at),
                _epoch_us(initial.updated_at),
                initial.revision,
            )
            connection.execute(
                """
                INSERT INTO experiment_attempt(
                    attempt_id, experiment_id, candidate_id, fold_id, ordinal,
                    parent_attempt_id, status, backtest_run_id, resume_from_run_id,
                    checkpoint_ref, reproduction_fingerprint, failure_code,
                    created_at_epoch_us, updated_at_epoch_us, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            self._insert_event(
                connection,
                subject_type="attempt",
                experiment_id=values[1],
                candidate_id=values[2],
                fold_id=values[3],
                attempt_id=values[0],
                revision=0,
                previous_status=None,
                status=initial.status,
                desired_state=None,
                stage=None,
                failure_code=None,
                reason_code="attempt_created",
                detail={},
                occurred_at=initial.created_at,
            )
            connection.commit()
            return (
                FoldProjection(
                    key,
                    ExperimentStatus.RUNNING,
                    lease_fence.owner_token,
                    datetime.fromtimestamp(
                        fold["created_at_epoch_us"] / 1_000_000,
                        tz=occurred_at.tzinfo,
                    ),
                    occurred_at,
                    new_fold_revision,
                ),
                initial,
            )
        except (
            ExperimentConflictError,
            ExperimentIntegrityError,
            ExperimentLeaseLostError,
            ExperimentSpecError,
        ):
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise _integrity(
                "atomic dispatch lineage or live-work constraint failed",
                "invalid_atomic_dispatch",
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "atomic fold dispatch failed and was rolled back",
                details={"reason_code": "atomic_dispatch_failed"},
            ) from exc

    @staticmethod
    def _validate_dispatch_attempt_lineage(
        connection: sqlite3.Connection,
        key: FoldKey,
        spec: AttemptPersistenceSpec,
    ) -> None:
        if spec.parent_attempt_id is None:
            return
        parent = connection.execute(
            "SELECT * FROM experiment_attempt WHERE attempt_id=?",
            (str(spec.parent_attempt_id),),
        ).fetchone()
        if parent is None or (
            parent["experiment_id"],
            parent["candidate_id"],
            parent["fold_id"],
        ) != (
            str(key.experiment_id),
            str(key.candidate_id),
            str(key.fold_id),
        ):
            raise _integrity(
                "retry parent lineage differs",
                "invalid_retry_parent_lineage",
            )
        if parent["ordinal"] >= spec.ordinal:
            raise _integrity(
                "retry parent ordinal is not smaller",
                "invalid_retry_parent_ordinal",
            )
        if parent["reproduction_fingerprint"] != str(spec.reproduction_fingerprint):
            raise _integrity("retry fingerprint drift", "retry_fingerprint_drift")
        if parent["status"] in {
            ExperimentStatus.QUEUED.value,
            ExperimentStatus.RUNNING.value,
        }:
            raise _integrity(
                "retry parent is still live",
                "retry_parent_not_terminal",
            )
        SQLiteAtomicDispatchMixin._validate_resume_source_lineage(
            connection,
            parent,
            spec.resume_from_run_id,
        )

    @staticmethod
    def _validate_resume_source_lineage(
        connection: sqlite3.Connection,
        parent: sqlite3.Row,
        resume_from_run_id: BacktestRunId | None,
    ) -> None:
        """Require a resume source to belong to the direct parent's ancestry."""
        if resume_from_run_id is None:
            return
        source = str(resume_from_run_id)
        ancestor: sqlite3.Row | None = parent
        while ancestor is not None:
            if ancestor["backtest_run_id"] == source:
                return
            parent_id = ancestor["parent_attempt_id"]
            if parent_id is None:
                break
            ancestor = connection.execute(
                "SELECT * FROM experiment_attempt WHERE attempt_id=?",
                (parent_id,),
            ).fetchone()
        raise _integrity(
            "retry resume source is outside the parent ancestry",
            "retry_resume_source_mismatch",
        )

    @staticmethod
    def _load_interrupted_work(
        connection: sqlite3.Connection,
        key: FoldKey,
        attempt_id: AttemptId,
        *,
        expected_fold_revision: int,
        expected_attempt_revision: int,
        current_owner_token: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        fold = connection.execute(
            """
            SELECT * FROM experiment_fold
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            """,
            (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
        ).fetchone()
        if fold is None:
            raise _integrity("fold does not exist", "fold_not_found")
        if fold["revision"] != expected_fold_revision:
            raise _conflict("fold revision is stale", "stale_projection_revision")
        if fold["status"] != ExperimentStatus.RUNNING.value:
            raise ExperimentSpecError(
                "crash recovery requires a running fold",
                details={"reason_code": "interrupted_fold_not_running"},
            )
        if (
            fold["claim_owner_token"] is None
            or fold["claim_owner_token"] == current_owner_token
        ):
            raise ExperimentSpecError(
                "crash recovery requires a fold orphaned by a prior owner",
                details={"reason_code": "crash_recovery_requires_reclaimed_owner"},
            )
        attempt = connection.execute(
            "SELECT * FROM experiment_attempt WHERE attempt_id=?",
            (str(attempt_id),),
        ).fetchone()
        expected_lineage = (
            str(key.experiment_id),
            str(key.candidate_id),
            str(key.fold_id),
        )
        if attempt is None:
            raise _integrity(
                "interrupted attempt lineage differs",
                "invalid_interrupted_attempt_lineage",
            )
        actual_lineage = (
            attempt["experiment_id"],
            attempt["candidate_id"],
            attempt["fold_id"],
        )
        if actual_lineage != expected_lineage:
            raise _integrity(
                "interrupted attempt lineage differs",
                "invalid_interrupted_attempt_lineage",
            )
        if attempt["revision"] != expected_attempt_revision:
            raise _conflict("attempt revision is stale", "stale_projection_revision")
        if attempt["status"] not in {
            ExperimentStatus.QUEUED.value,
            ExperimentStatus.RUNNING.value,
        }:
            raise ExperimentSpecError(
                "crash recovery requires a live interrupted attempt",
                details={"reason_code": "interrupted_attempt_not_live"},
            )
        return fold, attempt

    @staticmethod
    def _interrupted_attempt_projection(
        attempt: sqlite3.Row,
        attempt_id: AttemptId,
        occurred_at: datetime,
        revision: int,
    ) -> AttemptProjection:
        return AttemptProjection(
            attempt_id,
            ExperimentStatus.FAILED,
            (
                None
                if attempt["backtest_run_id"] is None
                else BacktestRunId(attempt["backtest_run_id"])
            ),
            (
                None
                if attempt["checkpoint_ref"] is None
                else CheckpointRef(attempt["checkpoint_ref"])
            ),
            ExperimentFailureCode.LEASE_LOST,
            datetime.fromtimestamp(
                attempt["created_at_epoch_us"] / 1_000_000,
                tz=occurred_at.tzinfo,
            ),
            occurred_at,
            revision,
        )

    @staticmethod
    def _validate_pause_requeue_preconditions(
        connection: sqlite3.Connection,
        key: FoldKey,
        expected_fold_revision: int,
    ) -> sqlite3.Row:
        parent = connection.execute(
            """
            SELECT status, desired_state FROM experiment
            WHERE experiment_id=?
            """,
            (str(key.experiment_id),),
        ).fetchone()
        if parent is None:
            raise _integrity("experiment does not exist", "experiment_not_found")
        if (
            parent["status"] != ExperimentStatus.PAUSE_REQUESTED.value
            or parent["desired_state"] != ExperimentDesiredState.PAUSE.value
        ):
            raise ExperimentSpecError(
                "pause fold requeue requires a pause-requested experiment",
                details={
                    "reason_code": "pause_requeue_not_requested",
                    "status": parent["status"],
                    "desired_state": parent["desired_state"],
                },
            )
        fold = connection.execute(
            """
            SELECT * FROM experiment_fold
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            """,
            (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
        ).fetchone()
        if fold is None:
            raise _integrity("fold does not exist", "fold_not_found")
        if fold["revision"] != expected_fold_revision:
            raise _conflict("fold revision is stale", "stale_projection_revision")
        if fold["status"] != ExperimentStatus.RUNNING.value:
            raise ExperimentSpecError(
                "pause recovery requires a running fold",
                details={
                    "reason_code": "pause_requeue_fold_not_running",
                    "status": fold["status"],
                },
            )
        if fold["claim_owner_token"] is None:
            raise _integrity(
                "running fold is missing its persisted claim owner",
                "running_fold_missing_claim_owner",
            )
        live_attempt = connection.execute(
            """
            SELECT attempt_id, status FROM experiment_attempt
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
              AND status IN ('queued', 'running')
            ORDER BY ordinal, attempt_id
            LIMIT 1
            """,
            (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
        ).fetchone()
        if live_attempt is not None:
            raise ExperimentSpecError(
                "pause recovery requires every fold attempt to be terminal",
                details={
                    "reason_code": "pause_requeue_live_attempt",
                    "attempt_id": live_attempt["attempt_id"],
                    "attempt_status": live_attempt["status"],
                },
            )
        return fold

    def requeue_fold_for_pause(
        self,
        key: FoldKey,
        *,
        expected_fold_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object],
    ) -> FoldProjection:
        """Explicitly unclaim a drained running fold during cooperative pause."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(
                connection,
                lease_fence,
                now_epoch_us,
                key.experiment_id,
            )
            fold = self._validate_pause_requeue_preconditions(
                connection,
                key,
                expected_fold_revision,
            )
            validate_fold_transition(
                ExperimentStatus.RUNNING,
                ExperimentStatus.QUEUED,
                claim_owner_token=None,
                fence_owner_token=lease_fence.owner_token,
                failure_code=None,
                reason_code="pause_recovery_requeue",
            )
            new_revision = expected_fold_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_fold
                SET status='queued', claim_owner_token=NULL,
                    updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND candidate_id=? AND fold_id=?
                  AND revision=? AND status='running'
                  AND claim_owner_token=?
                """,
                (
                    _epoch_us(occurred_at),
                    new_revision,
                    str(key.experiment_id),
                    str(key.candidate_id),
                    str(key.fold_id),
                    expected_fold_revision,
                    fold["claim_owner_token"],
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("fold CAS lost", "stale_projection_revision")
            self._insert_event(
                connection,
                subject_type="fold",
                experiment_id=str(key.experiment_id),
                candidate_id=str(key.candidate_id),
                fold_id=str(key.fold_id),
                attempt_id=None,
                revision=new_revision,
                previous_status=ExperimentStatus.RUNNING,
                status=ExperimentStatus.QUEUED,
                desired_state=None,
                stage=None,
                failure_code=None,
                reason_code="pause_recovery_requeue",
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return FoldProjection(
                key,
                ExperimentStatus.QUEUED,
                None,
                datetime.fromtimestamp(
                    fold["created_at_epoch_us"] / 1_000_000,
                    tz=occurred_at.tzinfo,
                ),
                occurred_at,
                new_revision,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise _integrity(
                "pause recovery lineage or event constraint failed",
                "invalid_pause_requeue",
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "pause fold requeue failed and was rolled back",
                details={"reason_code": "pause_requeue_failed"},
            ) from exc

    def requeue_interrupted_fold(
        self,
        key: FoldKey,
        attempt_id: AttemptId,
        *,
        expected_fold_revision: int,
        expected_attempt_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object],
    ) -> tuple[FoldProjection, AttemptProjection]:
        """Atomically terminate orphaned live work and requeue its fold."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(
                connection, lease_fence, now_epoch_us, key.experiment_id
            )
            fold, attempt = self._load_interrupted_work(
                connection,
                key,
                attempt_id,
                expected_fold_revision=expected_fold_revision,
                expected_attempt_revision=expected_attempt_revision,
                current_owner_token=lease_fence.owner_token,
            )
            validate_holdout_work_authority(
                connection,
                key,
                ContentHash(attempt["reproduction_fingerprint"]),
            )
            previous_attempt_status = ExperimentStatus(attempt["status"])
            previous_fold_status = ExperimentStatus(fold["status"])
            validate_fold_transition(
                previous_fold_status,
                ExperimentStatus.QUEUED,
                claim_owner_token=None,
                fence_owner_token=lease_fence.owner_token,
                failure_code=None,
                reason_code="crash_recovery",
            )
            attempt_revision = expected_attempt_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_attempt
                SET status='failed', failure_code='lease_lost',
                    updated_at_epoch_us=?, revision=?
                WHERE attempt_id=? AND revision=? AND status IN ('queued', 'running')
                """,
                (
                    _epoch_us(occurred_at),
                    attempt_revision,
                    str(attempt_id),
                    expected_attempt_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("attempt CAS lost", "stale_projection_revision")
            self._insert_event(
                connection,
                subject_type="attempt",
                experiment_id=attempt["experiment_id"],
                candidate_id=attempt["candidate_id"],
                fold_id=attempt["fold_id"],
                attempt_id=attempt["attempt_id"],
                revision=attempt_revision,
                previous_status=previous_attempt_status,
                status=ExperimentStatus.FAILED,
                desired_state=None,
                stage=None,
                failure_code=ExperimentFailureCode.LEASE_LOST,
                reason_code="crash_recovery_interrupted",
                detail=detail,
                occurred_at=occurred_at,
            )
            fold_revision = expected_fold_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_fold
                SET status='queued', claim_owner_token=NULL,
                    updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND candidate_id=? AND fold_id=?
                  AND revision=? AND status='running'
                """,
                (
                    _epoch_us(occurred_at),
                    fold_revision,
                    str(key.experiment_id),
                    str(key.candidate_id),
                    str(key.fold_id),
                    expected_fold_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("fold CAS lost", "stale_projection_revision")
            self._insert_event(
                connection,
                subject_type="fold",
                experiment_id=str(key.experiment_id),
                candidate_id=str(key.candidate_id),
                fold_id=str(key.fold_id),
                attempt_id=None,
                revision=fold_revision,
                previous_status=previous_fold_status,
                status=ExperimentStatus.QUEUED,
                desired_state=None,
                stage=None,
                failure_code=None,
                reason_code="crash_recovery_requeue",
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return (
                FoldProjection(
                    key,
                    ExperimentStatus.QUEUED,
                    None,
                    datetime.fromtimestamp(
                        fold["created_at_epoch_us"] / 1_000_000,
                        tz=occurred_at.tzinfo,
                    ),
                    occurred_at,
                    fold_revision,
                ),
                self._interrupted_attempt_projection(
                    attempt,
                    attempt_id,
                    occurred_at,
                    attempt_revision,
                ),
            )
        except (
            ExperimentConflictError,
            ExperimentIntegrityError,
            ExperimentLeaseLostError,
            ExperimentSpecError,
        ):
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise _integrity(
                "crash recovery lineage or event constraint failed",
                "invalid_crash_recovery",
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "crash recovery failed and was rolled back",
                details={"reason_code": "crash_recovery_failed"},
            ) from exc
