"""Atomic fenced dispatch of a fold and its first attempt."""

# Approved typed command surfaces intentionally carry explicit fencing/event fields.
# ruff: noqa: PLR0913

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime

from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
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
from ditto_analysis.storage.sqlite.experiments._work_rules import (
    validate_attempt_fold_owner,
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
        if (
            spec.ordinal != 1
            or spec.parent_attempt_id is not None
            or spec.resume_from_run_id is not None
        ):
            raise ExperimentSpecError(
                "atomic fold dispatch accepts only a first, non-resumed attempt",
                details={"reason_code": "atomic_dispatch_requires_first_attempt"},
            )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(
                connection, lease_fence, now_epoch_us, key.experiment_id
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
