"""Insert-only commands, revisioned projections, and lease fencing for experiments."""

# Approved typed command surfaces intentionally carry explicit fencing/event fields.
# ruff: noqa: PLR0913

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from datetime import datetime

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
    AttemptId,
    BacktestRunId,
    CheckpointRef,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    validate_status_transition,
)
from ditto_analysis.experiments.persistence import (
    AttemptPersistenceSpec,
    AttemptProjection,
    ExperimentProjection,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    LeaseFence,
)
from ditto_analysis.storage.sqlite.experiments._creation import (
    SQLiteExperimentCreationMixin,
)
from ditto_analysis.storage.sqlite.experiments._dispatch import (
    SQLiteAtomicDispatchMixin,
)
from ditto_analysis.storage.sqlite.experiments._experiment_control import (
    SQLiteExperimentControlMixin,
    validate_experiment_status_stage_transition,
)
from ditto_analysis.storage.sqlite.experiments._experiment_rules import (
    validate_operator_experiment_transition,
)
from ditto_analysis.storage.sqlite.experiments._facts import (
    SQLiteExperimentFactsMixin,
)
from ditto_analysis.storage.sqlite.experiments._work_rules import (
    validate_attempt_fold_owner,
    validate_attempt_start_dispatchable,
    validate_attempt_transition,
    validate_experiment_dispatchable,
    validate_fold_transition,
    validate_new_fold_creation_allowed,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)
from ditto_analysis.storage.sqlite.experiments.reader import SQLiteExperimentReader

_WORK_STATUSES = frozenset(
    {
        ExperimentStatus.QUEUED,
        ExperimentStatus.RUNNING,
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
    }
)


def _epoch_us(value: datetime) -> int:
    require_utc_datetime(value, "datetime")
    return int(value.timestamp() * 1_000_000)


def _persistence_error(
    message: str, reason_code: str, **details: object
) -> ExperimentPersistenceError:
    return ExperimentPersistenceError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _integrity(
    message: str, reason_code: str, **details: object
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _conflict(
    message: str, reason_code: str, **details: object
) -> ExperimentConflictError:
    return ExperimentConflictError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _optional(value: object | None) -> str | None:
    return None if value is None else str(value)


class SQLiteExperimentWriter(
    SQLiteExperimentCreationMixin,
    SQLiteExperimentFactsMixin,
    SQLiteAtomicDispatchMixin,
    SQLiteExperimentControlMixin,
):
    """Implement the approved aggregate, evidence, CAS, and lease commands."""

    def __init__(self, database: ResearchExperimentDatabase) -> None:
        self._database = database
        self._reader = SQLiteExperimentReader(database)

    def transition_experiment(
        self,
        experiment_id: ExperimentId,
        *,
        target_status: ExperimentStatus,
        target_desired_state: ExperimentDesiredState,
        target_stage: ExperimentStage,
        failure_code: ExperimentFailureCode | None,
        expected_revision: int,
        occurred_at: datetime,
        attempt_started: bool,
        precondition_repairable: bool,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection:
        """CAS one legal experiment transition and append its matching event."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM experiment WHERE experiment_id=?", (str(experiment_id),)
            ).fetchone()
            if row is None:
                raise _integrity("experiment does not exist", "experiment_not_found")
            if row["revision"] != expected_revision:
                raise _conflict(
                    "experiment revision is stale",
                    "stale_projection_revision",
                    expected_revision=expected_revision,
                    actual_revision=row["revision"],
                )
            current_status = ExperimentStatus(row["status"])
            validate_status_transition(
                current_status,
                target_status,
                attempt_started=attempt_started,
                precondition_repairable=precondition_repairable,
            )
            current_desired_state = ExperimentDesiredState(row["desired_state"])
            validate_operator_experiment_transition(
                current_status,
                current_desired_state,
                target_status,
                target_desired_state,
            )
            validate_experiment_status_stage_transition(
                current_status,
                ExperimentStage(row["stage"]),
                target_status,
                target_stage,
            )
            created_at = datetime.fromtimestamp(
                row["created_at_epoch_us"] / 1_000_000, tz=occurred_at.tzinfo
            )
            record = ExperimentRecord(
                experiment_id=experiment_id,
                status=target_status,
                desired_state=target_desired_state,
                stage=target_stage,
                created_at=created_at,
                failure_code=failure_code,
            )
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment
                SET status=?, desired_state=?, stage=?, failure_code=?,
                    updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND revision=?
                """,
                (
                    target_status.value,
                    target_desired_state.value,
                    target_stage.value,
                    _optional(failure_code),
                    _epoch_us(occurred_at),
                    new_revision,
                    str(experiment_id),
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("experiment CAS lost", "stale_projection_revision")
            self._insert_event(
                connection,
                subject_type="experiment",
                experiment_id=str(experiment_id),
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                revision=new_revision,
                previous_status=current_status,
                status=target_status,
                desired_state=target_desired_state,
                stage=target_stage,
                failure_code=failure_code,
                reason_code=reason_code,
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return ExperimentProjection(
                record, row["queue_ordinal"], new_revision, occurred_at
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "experiment transition failed and was rolled back",
                "experiment_transition_failed",
                sqlite_error=type(exc).__name__,
            ) from exc

    def add_fold(self, spec: FoldPersistenceSpec, initial: FoldProjection) -> None:
        """Insert one immutable fold and its revision-zero event atomically."""
        self._validate_fold(spec, initial)
        train_start = (
            None if spec.train_window is None else spec.train_window.start.isoformat()
        )
        train_end = (
            None if spec.train_window is None else spec.train_window.end.isoformat()
        )
        values = (
            str(spec.key.experiment_id),
            str(spec.key.candidate_id),
            str(spec.key.fold_id),
            spec.ordinal,
            spec.fold_role.value,
            train_start,
            train_end,
            spec.test_window.start.isoformat(),
            spec.test_window.end.isoformat(),
            spec.purge_sessions,
            spec.embargo_sessions,
            spec.canonical_payload.decode("utf-8"),
            str(spec.payload_hash),
            initial.status.value,
            initial.claim_owner_token,
            _epoch_us(initial.created_at),
            _epoch_us(initial.updated_at),
            initial.revision,
        )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM experiment_fold
                WHERE experiment_id=? AND candidate_id=? AND fold_id=?
                """,
                values[:3],
            ).fetchone()
            if existing is not None:
                self._verify_fold_replay(connection, existing, values, initial)
                connection.commit()
                return
            validate_new_fold_creation_allowed(connection, spec.key.experiment_id)
            connection.execute(
                """
                INSERT INTO experiment_fold(
                    experiment_id, candidate_id, fold_id, ordinal, fold_role,
                    train_start, train_end, test_start, test_end, purge_sessions,
                    embargo_sessions, fold_spec_json, fold_spec_hash, status,
                    claim_owner_token, created_at_epoch_us, updated_at_epoch_us,
                    revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            self._insert_event(
                connection,
                subject_type="fold",
                experiment_id=values[0],
                candidate_id=values[1],
                fold_id=values[2],
                attempt_id=None,
                revision=0,
                previous_status=None,
                status=initial.status,
                desired_state=None,
                stage=None,
                failure_code=None,
                reason_code="fold_created",
                detail={},
                occurred_at=initial.created_at,
            )
            connection.commit()
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise _integrity(
                "fold lineage or uniqueness constraint failed",
                "invalid_fold_lineage",
                sqlite_error=type(exc).__name__,
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "fold insert failed", "fold_insert_failed"
            ) from exc

    @staticmethod
    def _validate_fold(spec: FoldPersistenceSpec, initial: FoldProjection) -> None:
        if (
            initial.key != spec.key
            or initial.status is not ExperimentStatus.QUEUED
            or initial.claim_owner_token is not None
            or initial.revision != 0
            or initial.updated_at != initial.created_at
            or type(spec.ordinal) is not int
            or spec.ordinal <= 0
            or type(spec.purge_sessions) is not int
            or spec.purge_sessions < 0
            or type(spec.embargo_sessions) is not int
            or spec.embargo_sessions < 0
            or (spec.fold_role is FoldRole.EXPLORATION) != (spec.train_window is None)
        ):
            raise ExperimentSpecError(
                "fold initial projection or relation is invalid",
                details={"reason_code": "invalid_initial_fold_projection"},
            )
        if hashlib.sha256(spec.canonical_payload).hexdigest() != str(spec.payload_hash):
            raise ExperimentSpecError(
                "fold payload hash mismatch",
                details={"reason_code": "fold_payload_hash_mismatch"},
            )
        expected = FoldPersistenceSpec.create(
            key=spec.key,
            ordinal=spec.ordinal,
            fold_role=spec.fold_role,
            train_window=spec.train_window,
            test_window=spec.test_window,
            purge_sessions=spec.purge_sessions,
            embargo_sessions=spec.embargo_sessions,
        )
        if expected.canonical_payload != spec.canonical_payload:
            raise ExperimentSpecError(
                "fold payload disagrees with its relational fields",
                details={"reason_code": "fold_relation_payload_mismatch"},
            )

    def add_attempt(
        self,
        spec: AttemptPersistenceSpec,
        initial: AttemptProjection,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> None:
        """Insert one lineage-validated attempt and revision-zero event."""
        self._validate_initial_attempt(spec, initial)
        values = (
            str(spec.attempt_id),
            str(spec.fold_key.experiment_id),
            str(spec.fold_key.candidate_id),
            str(spec.fold_key.fold_id),
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
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM experiment_attempt WHERE attempt_id=?",
                (str(spec.attempt_id),),
            ).fetchone()
            if existing is not None:
                self._verify_attempt_replay(connection, existing, values, initial)
                connection.commit()
                return
            self._validate_lease(
                connection, lease_fence, now_epoch_us, spec.fold_key.experiment_id
            )
            validate_experiment_dispatchable(connection, spec.fold_key.experiment_id)
            validate_attempt_fold_owner(
                connection, spec.fold_key, lease_fence.owner_token
            )
            if spec.parent_attempt_id is not None:
                parent = connection.execute(
                    "SELECT * FROM experiment_attempt WHERE attempt_id=?",
                    (str(spec.parent_attempt_id),),
                ).fetchone()
                if (
                    parent is None
                    or (
                        parent["experiment_id"],
                        parent["candidate_id"],
                        parent["fold_id"],
                    )
                    != values[1:4]
                ):
                    raise _integrity(
                        "retry parent lineage differs", "invalid_retry_parent_lineage"
                    )
                if parent["ordinal"] >= spec.ordinal:
                    raise _integrity(
                        "retry parent ordinal is not smaller",
                        "invalid_retry_parent_ordinal",
                    )
                if parent["reproduction_fingerprint"] != str(
                    spec.reproduction_fingerprint
                ):
                    raise _integrity(
                        "retry fingerprint drift", "retry_fingerprint_drift"
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
                failure_code=initial.failure_code,
                reason_code="attempt_created",
                detail={},
                occurred_at=initial.created_at,
            )
            connection.commit()
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise _integrity(
                "attempt lineage or live-work constraint failed",
                "invalid_attempt_lineage",
                sqlite_error=type(exc).__name__,
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "attempt insert failed", "attempt_insert_failed"
            ) from exc

    @staticmethod
    def _validate_initial_attempt(
        spec: AttemptPersistenceSpec, initial: AttemptProjection
    ) -> None:
        if (
            initial.attempt_id != spec.attempt_id
            or initial.status is not ExperimentStatus.QUEUED
            or initial.backtest_run_id is not None
            or initial.checkpoint_ref is not None
            or initial.failure_code is not None
            or initial.created_at != spec.created_at
            or initial.updated_at != spec.created_at
            or initial.revision != 0
            or spec.ordinal <= 0
            or (spec.ordinal == 1) != (spec.parent_attempt_id is None)
        ):
            raise ExperimentSpecError(
                "attempt initial projection or immutable lineage is invalid",
                details={"reason_code": "invalid_initial_attempt_projection"},
            )

    def claim_fold(
        self,
        key: FoldKey,
        *,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> FoldProjection:
        """Claim queued fold work with the current unexpired scheduler fence."""
        return self.transition_fold(
            key,
            target_status=ExperimentStatus.RUNNING,
            claim_owner_token=lease_fence.owner_token,
            failure_code=None,
            expected_revision=expected_revision,
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            reason_code="fold_claimed",
            detail={},
        )

    def transition_fold(
        self,
        key: FoldKey,
        *,
        target_status: ExperimentStatus,
        claim_owner_token: str | None,
        failure_code: ExperimentFailureCode | None,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> FoldProjection:
        """CAS a fold projection under a current scheduler fence."""
        if target_status not in _WORK_STATUSES:
            raise ExperimentSpecError(
                "fold target status is invalid",
                details={"reason_code": "invalid_fold_status"},
            )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(
                connection, lease_fence, now_epoch_us, key.experiment_id
            )
            if target_status is ExperimentStatus.RUNNING:
                validate_experiment_dispatchable(connection, key.experiment_id)
            row = connection.execute(
                """
                SELECT * FROM experiment_fold
                WHERE experiment_id=? AND candidate_id=? AND fold_id=?
                """,
                (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
            ).fetchone()
            if row is None:
                raise _integrity("fold does not exist", "fold_not_found")
            if row["revision"] != expected_revision:
                raise _conflict("fold revision is stale", "stale_projection_revision")
            previous_status = ExperimentStatus(row["status"])
            if (
                previous_status is ExperimentStatus.RUNNING
                and target_status is ExperimentStatus.QUEUED
            ):
                raise ExperimentSpecError(
                    "running fold recovery requires an atomic recovery operation",
                    details={"reason_code": "recovery_transition_requires_atomic_api"},
                )
            validate_fold_transition(
                previous_status,
                target_status,
                claim_owner_token=claim_owner_token,
                fence_owner_token=lease_fence.owner_token,
                failure_code=failure_code,
                reason_code=reason_code,
            )
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_fold
                SET status=?, claim_owner_token=?, updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND candidate_id=? AND fold_id=? AND revision=?
                """,
                (
                    target_status.value,
                    claim_owner_token,
                    _epoch_us(occurred_at),
                    new_revision,
                    str(key.experiment_id),
                    str(key.candidate_id),
                    str(key.fold_id),
                    expected_revision,
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
                previous_status=previous_status,
                status=target_status,
                desired_state=None,
                stage=None,
                failure_code=failure_code,
                reason_code=reason_code,
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return FoldProjection(
                key,
                target_status,
                claim_owner_token,
                datetime.fromtimestamp(
                    row["created_at_epoch_us"] / 1_000_000, tz=occurred_at.tzinfo
                ),
                occurred_at,
                new_revision,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "fold transition failed", "fold_transition_failed"
            ) from exc

    def transition_attempt(
        self,
        attempt_id: AttemptId,
        *,
        target_status: ExperimentStatus,
        backtest_run_id: BacktestRunId | None,
        checkpoint_ref: CheckpointRef | None,
        failure_code: ExperimentFailureCode | None,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> AttemptProjection:
        """CAS attempt status, checkpoint, or result under a current fence."""
        if target_status not in _WORK_STATUSES:
            raise ExperimentSpecError(
                "attempt target status is invalid",
                details={"reason_code": "invalid_attempt_status"},
            )
        # Constructing this projection is also the full failure/status policy check.
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM experiment_attempt WHERE attempt_id=?",
                (str(attempt_id),),
            ).fetchone()
            if row is None:
                raise _integrity("attempt does not exist", "attempt_not_found")
            experiment_id = ExperimentId(row["experiment_id"])
            self._validate_lease(connection, lease_fence, now_epoch_us, experiment_id)
            if row["revision"] != expected_revision:
                raise _conflict(
                    "attempt revision is stale", "stale_projection_revision"
                )
            previous_status = ExperimentStatus(row["status"])
            validate_attempt_transition(previous_status, target_status)
            validate_attempt_start_dispatchable(
                connection,
                experiment_id,
                previous_status,
                target_status,
            )
            if (
                target_status in (ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED)
                and backtest_run_id is None
            ):
                raise ExperimentSpecError(
                    "running/completed attempt requires backtest run identity",
                    details={"reason_code": "backtest_run_identity_required"},
                )
            if target_status is ExperimentStatus.FAILED and failure_code is None:
                raise ExperimentSpecError(
                    "failed attempt requires failure code",
                    details={"reason_code": "failure_code_required"},
                )
            if (
                target_status is not ExperimentStatus.FAILED
                and failure_code is not None
            ):
                raise ExperimentSpecError(
                    "non-failed attempt cannot have failure code",
                    details={"reason_code": "failure_code_without_failure_outcome"},
                )
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_attempt
                SET status=?, backtest_run_id=?, checkpoint_ref=?, failure_code=?,
                    updated_at_epoch_us=?, revision=?
                WHERE attempt_id=? AND revision=?
                """,
                (
                    target_status.value,
                    _optional(backtest_run_id),
                    _optional(checkpoint_ref),
                    _optional(failure_code),
                    _epoch_us(occurred_at),
                    new_revision,
                    str(attempt_id),
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("attempt CAS lost", "stale_projection_revision")
            self._insert_event(
                connection,
                subject_type="attempt",
                experiment_id=row["experiment_id"],
                candidate_id=row["candidate_id"],
                fold_id=row["fold_id"],
                attempt_id=row["attempt_id"],
                revision=new_revision,
                previous_status=previous_status,
                status=target_status,
                desired_state=None,
                stage=None,
                failure_code=failure_code,
                reason_code=reason_code,
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return AttemptProjection(
                attempt_id,
                target_status,
                backtest_run_id,
                checkpoint_ref,
                failure_code,
                datetime.fromtimestamp(
                    row["created_at_epoch_us"] / 1_000_000, tz=occurred_at.tzinfo
                ),
                occurred_at,
                new_revision,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "attempt transition failed", "attempt_transition_failed"
            ) from exc
