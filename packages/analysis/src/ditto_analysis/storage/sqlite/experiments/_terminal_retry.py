"""Fenced recovery of terminal system-failed experiment folds."""

# Approved typed command surfaces intentionally carry explicit fencing/event fields.
# ruff: noqa: PLR0913

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import cast

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
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import FoldKey, FoldProjection, LeaseFence
from ditto_analysis.storage.sqlite.experiments._work_rules import (
    validate_terminal_fold_retry_experiment,
    validate_terminal_fold_retry_parent,
    validate_terminal_fold_retry_target,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)


def _epoch_us(value: datetime) -> int:
    require_utc_datetime(value, "datetime")
    return int(value.timestamp() * 1_000_000)


def _conflict(message: str, reason_code: str) -> ExperimentConflictError:
    return ExperimentConflictError(message, details={"reason_code": reason_code})


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


class SQLiteTerminalFoldRetryMixin:
    """Atomically requeue an eligible failed fold under the active lease fence."""

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

    @staticmethod
    def _load_terminal_retry_fold(
        connection: sqlite3.Connection,
        key: FoldKey,
        expected_fold_revision: int,
    ) -> tuple[sqlite3.Row, ExperimentFailureCode]:
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
        fold_event = connection.execute(
            """
            SELECT status, failure_code FROM experiment_status_event
            WHERE subject_type='fold'
              AND experiment_id=? AND candidate_id=? AND fold_id=?
              AND subject_revision=?
            """,
            (
                str(key.experiment_id),
                str(key.candidate_id),
                str(key.fold_id),
                expected_fold_revision,
            ),
        ).fetchone()
        if fold_event is None or fold_event["status"] != fold["status"]:
            raise _integrity(
                "terminal fold projection and status event differ",
                "terminal_fold_retry_event_invalid",
            )
        failure_code = (
            None
            if fold_event["failure_code"] is None
            else ExperimentFailureCode(fold_event["failure_code"])
        )
        validate_terminal_fold_retry_target(
            fold_status=ExperimentStatus(fold["status"]),
            fold_failure_code=failure_code,
        )
        return fold, cast(ExperimentFailureCode, failure_code)

    @staticmethod
    def _load_terminal_retry_parent(
        connection: sqlite3.Connection,
        key: FoldKey,
        parent_attempt_id: AttemptId,
        *,
        expected_parent_attempt_revision: int,
        fold_failure_code: ExperimentFailureCode,
    ) -> sqlite3.Row:
        lineage_values = (
            str(key.experiment_id),
            str(key.candidate_id),
            str(key.fold_id),
        )
        live_attempt = connection.execute(
            """
            SELECT attempt_id, status FROM experiment_attempt
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
              AND status IN ('queued', 'running')
            ORDER BY ordinal, attempt_id
            LIMIT 1
            """,
            lineage_values,
        ).fetchone()
        if live_attempt is not None:
            raise ExperimentSpecError(
                "terminal fold retry cannot coexist with live attempt work",
                details={
                    "reason_code": "terminal_fold_retry_live_attempt",
                    "attempt_id": live_attempt["attempt_id"],
                    "attempt_status": live_attempt["status"],
                },
            )
        latest_parent = connection.execute(
            """
            SELECT * FROM experiment_attempt
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            ORDER BY ordinal DESC, attempt_id DESC
            LIMIT 1
            """,
            lineage_values,
        ).fetchone()
        if latest_parent is None:
            raise _integrity(
                "terminal fold retry parent lineage differs",
                "terminal_fold_retry_parent_lineage_invalid",
            )
        if latest_parent["attempt_id"] != str(parent_attempt_id):
            supplied_parent = connection.execute(
                "SELECT * FROM experiment_attempt WHERE attempt_id=?",
                (str(parent_attempt_id),),
            ).fetchone()
            if (
                supplied_parent is not None
                and (
                    supplied_parent["experiment_id"],
                    supplied_parent["candidate_id"],
                    supplied_parent["fold_id"],
                )
                == lineage_values
            ):
                raise ExperimentSpecError(
                    "terminal fold retry requires the latest parent attempt",
                    details={
                        "reason_code": "terminal_fold_retry_parent_not_latest",
                        "latest_attempt_id": latest_parent["attempt_id"],
                        "parent_attempt_id": str(parent_attempt_id),
                    },
                )
            raise _integrity(
                "terminal fold retry parent lineage differs",
                "terminal_fold_retry_parent_lineage_invalid",
            )
        if latest_parent["revision"] != expected_parent_attempt_revision:
            raise _conflict(
                "parent attempt revision is stale",
                "stale_projection_revision",
            )
        parent_failure_code = (
            None
            if latest_parent["failure_code"] is None
            else ExperimentFailureCode(latest_parent["failure_code"])
        )
        validate_terminal_fold_retry_parent(
            parent_status=ExperimentStatus(latest_parent["status"]),
            parent_failure_code=parent_failure_code,
            fold_failure_code=fold_failure_code,
        )
        return latest_parent

    def requeue_failed_fold_for_retry(
        self,
        key: FoldKey,
        parent_attempt_id: AttemptId,
        *,
        expected_fold_revision: int,
        expected_parent_attempt_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object],
    ) -> FoldProjection:
        """Explicitly requeue a system/lease failed fold for a successor attempt."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            experiment = connection.execute(
                """
                SELECT status, desired_state FROM experiment
                WHERE experiment_id=?
                """,
                (str(key.experiment_id),),
            ).fetchone()
            if experiment is None:
                raise _integrity("experiment does not exist", "experiment_not_found")
            validate_terminal_fold_retry_experiment(
                experiment_status=ExperimentStatus(experiment["status"]),
                desired_state=ExperimentDesiredState(experiment["desired_state"]),
            )
            self._validate_lease(
                connection,
                lease_fence,
                now_epoch_us,
                key.experiment_id,
            )
            fold, fold_failure_code = self._load_terminal_retry_fold(
                connection,
                key,
                expected_fold_revision,
            )
            self._load_terminal_retry_parent(
                connection,
                key,
                parent_attempt_id,
                expected_parent_attempt_revision=expected_parent_attempt_revision,
                fold_failure_code=fold_failure_code,
            )
            occurred_at_epoch_us = _epoch_us(occurred_at)
            new_revision = expected_fold_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_fold
                SET status='queued', claim_owner_token=NULL,
                    updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND candidate_id=? AND fold_id=?
                  AND revision=? AND status='failed'
                """,
                (
                    occurred_at_epoch_us,
                    new_revision,
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
                revision=new_revision,
                previous_status=ExperimentStatus.FAILED,
                status=ExperimentStatus.QUEUED,
                desired_state=None,
                stage=None,
                failure_code=None,
                reason_code="terminal_fold_retry",
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
                "terminal fold retry lineage or event constraint failed",
                "invalid_terminal_fold_retry",
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "terminal fold retry failed and was rolled back",
                details={"reason_code": "terminal_fold_retry_failed"},
            ) from exc
