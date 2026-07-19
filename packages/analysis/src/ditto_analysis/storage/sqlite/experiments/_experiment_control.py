"""Atomic queue allocation and lease-fenced experiment scheduler commands."""

# Command fields stay explicit at this persistence boundary.
# ruff: noqa: PLR0913

from __future__ import annotations

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
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    validate_status_transition,
)
from ditto_analysis.experiments.persistence import ExperimentProjection, LeaseFence
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)

_NEXT_RUNNING_STAGE = {
    ExperimentStage.EXPLORATION: ExperimentStage.WALK_FORWARD,
    ExperimentStage.WALK_FORWARD: ExperimentStage.CANDIDATE_SELECTION,
    ExperimentStage.CANDIDATE_SELECTION: ExperimentStage.HOLDOUT,
    ExperimentStage.HOLDOUT: ExperimentStage.EVIDENCE,
}


def validate_experiment_status_stage_transition(
    current_status: ExperimentStatus,
    current_stage: ExperimentStage,
    target_status: ExperimentStatus,
    target_stage: ExperimentStage,
) -> None:
    """Keep stage orthogonal to status except for fenced scheduler dispatch."""
    if (
        current_status is ExperimentStatus.QUEUED
        and target_status is ExperimentStatus.RUNNING
    ):
        if target_stage is not ExperimentStage.EXPLORATION:
            raise ExperimentSpecError(
                "scheduler dispatch must enter exploration",
                details={"reason_code": "scheduler_dispatch_requires_exploration"},
            )
    elif target_stage is not current_stage:
        raise ExperimentSpecError(
            "status or desired-state transitions must preserve experiment stage",
            details={"reason_code": "experiment_stage_must_be_preserved"},
        )
    if (
        target_status
        in (
            ExperimentStatus.COMPLETED,
            ExperimentStatus.COMPLETED_WITH_FAILURES,
        )
        and target_stage is not ExperimentStage.EVIDENCE
    ):
        raise ExperimentSpecError(
            "completed experiment must already be in evidence stage",
            details={"reason_code": "terminal_stage_not_evidence"},
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


class SQLiteExperimentControlMixin:
    """Provide queue allocation and scheduler-only experiment transitions."""

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

    def enqueue_experiment(
        self,
        experiment_id: ExperimentId,
        *,
        expected_revision: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection:
        """Allocate the next queue ordinal and append the CAS event atomically."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM experiment WHERE experiment_id=?",
                (str(experiment_id),),
            ).fetchone()
            if row is None:
                raise _integrity("experiment does not exist", "experiment_not_found")
            if row["revision"] != expected_revision:
                raise _conflict(
                    "experiment revision is stale", "stale_projection_revision"
                )
            current_status = ExperimentStatus(row["status"])
            validate_status_transition(
                current_status,
                ExperimentStatus.QUEUED,
                attempt_started=False,
                precondition_repairable=False,
            )
            if row["queue_ordinal"] is not None:
                raise _conflict(
                    "experiment queue ordinal is already allocated",
                    "queue_ordinal_already_allocated",
                )
            queue_ordinal = connection.execute(
                "SELECT coalesce(max(queue_ordinal), 0) + 1 FROM experiment"
            ).fetchone()[0]
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment
                SET queue_ordinal=?, status='queued', updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND revision=? AND queue_ordinal IS NULL
                """,
                (
                    queue_ordinal,
                    _epoch_us(occurred_at),
                    new_revision,
                    str(experiment_id),
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict(
                    "experiment enqueue CAS lost", "stale_projection_revision"
                )
            desired_state = ExperimentDesiredState(row["desired_state"])
            stage = ExperimentStage(row["stage"])
            self._insert_event(
                connection,
                subject_type="experiment",
                experiment_id=str(experiment_id),
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                revision=new_revision,
                previous_status=current_status,
                status=ExperimentStatus.QUEUED,
                desired_state=desired_state,
                stage=stage,
                failure_code=None,
                reason_code=reason_code,
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return ExperimentProjection(
                ExperimentRecord(
                    experiment_id,
                    ExperimentStatus.QUEUED,
                    desired_state,
                    stage,
                    datetime.fromtimestamp(
                        row["created_at_epoch_us"] / 1_000_000,
                        tz=occurred_at.tzinfo,
                    ),
                ),
                queue_ordinal,
                new_revision,
                occurred_at,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "experiment enqueue failed and was rolled back",
                details={"reason_code": "experiment_enqueue_failed"},
            ) from exc

    def transition_scheduled_experiment(
        self,
        experiment_id: ExperimentId,
        *,
        target_status: ExperimentStatus,
        target_stage: ExperimentStage,
        failure_code: ExperimentFailureCode | None,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        attempt_started: bool,
        precondition_repairable: bool,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection:
        """Apply a scheduler transition only under the current global fence."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(connection, lease_fence, now_epoch_us, experiment_id)
            row = connection.execute(
                "SELECT * FROM experiment WHERE experiment_id=?",
                (str(experiment_id),),
            ).fetchone()
            if row is None:
                raise _integrity("experiment does not exist", "experiment_not_found")
            if row["revision"] != expected_revision:
                raise _conflict(
                    "experiment revision is stale", "stale_projection_revision"
                )
            current_status = ExperimentStatus(row["status"])
            validate_status_transition(
                current_status,
                target_status,
                attempt_started=attempt_started,
                precondition_repairable=precondition_repairable,
            )
            validate_experiment_status_stage_transition(
                current_status,
                ExperimentStage(row["stage"]),
                target_status,
                target_stage,
            )
            desired_state = ExperimentDesiredState(row["desired_state"])
            record = ExperimentRecord(
                experiment_id,
                target_status,
                desired_state,
                target_stage,
                datetime.fromtimestamp(
                    row["created_at_epoch_us"] / 1_000_000,
                    tz=occurred_at.tzinfo,
                ),
                failure_code,
            )
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment
                SET status=?, stage=?, failure_code=?, updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND revision=?
                """,
                (
                    target_status.value,
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
                desired_state=desired_state,
                stage=target_stage,
                failure_code=failure_code,
                reason_code=reason_code,
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return ExperimentProjection(
                record,
                row["queue_ordinal"],
                new_revision,
                occurred_at,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "scheduled experiment transition failed and was rolled back",
                details={"reason_code": "scheduled_experiment_transition_failed"},
            ) from exc

    def advance_experiment_stage(
        self,
        experiment_id: ExperimentId,
        *,
        target_stage: ExperimentStage,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection:
        """Advance one running-stage edge under the current scheduler fence."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(connection, lease_fence, now_epoch_us, experiment_id)
            row = connection.execute(
                "SELECT * FROM experiment WHERE experiment_id=?",
                (str(experiment_id),),
            ).fetchone()
            if row is None:
                raise _integrity("experiment does not exist", "experiment_not_found")
            if row["revision"] != expected_revision:
                raise _conflict(
                    "experiment revision is stale", "stale_projection_revision"
                )
            current_status = ExperimentStatus(row["status"])
            current_stage = ExperimentStage(row["stage"])
            if (
                current_status is not ExperimentStatus.RUNNING
                or _NEXT_RUNNING_STAGE.get(current_stage) is not target_stage
            ):
                raise ExperimentSpecError(
                    "invalid running stage transition: "
                    + f"{current_stage.value} -> {target_stage.value}",
                    details={
                        "reason_code": "invalid_experiment_stage_transition",
                        "current_stage": current_stage.value,
                        "target_stage": target_stage.value,
                    },
                )
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment
                SET stage=?, updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND revision=? AND status='running'
                """,
                (
                    target_stage.value,
                    _epoch_us(occurred_at),
                    new_revision,
                    str(experiment_id),
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict(
                    "experiment stage CAS lost", "stale_projection_revision"
                )
            desired_state = ExperimentDesiredState(row["desired_state"])
            failure_code = (
                None
                if row["failure_code"] is None
                else ExperimentFailureCode(row["failure_code"])
            )
            self._insert_event(
                connection,
                subject_type="experiment",
                experiment_id=str(experiment_id),
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                revision=new_revision,
                previous_status=current_status,
                status=current_status,
                desired_state=desired_state,
                stage=target_stage,
                failure_code=failure_code,
                reason_code=reason_code,
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            record = ExperimentRecord(
                experiment_id,
                current_status,
                desired_state,
                target_stage,
                datetime.fromtimestamp(
                    row["created_at_epoch_us"] / 1_000_000,
                    tz=occurred_at.tzinfo,
                ),
                failure_code,
            )
            return ExperimentProjection(
                record,
                row["queue_ordinal"],
                new_revision,
                occurred_at,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "experiment stage advance failed and was rolled back",
                details={"reason_code": "experiment_stage_advance_failed"},
            ) from exc
