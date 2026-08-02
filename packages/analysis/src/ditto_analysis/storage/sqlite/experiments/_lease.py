"""Singleton scheduler lease commands shared by the experiment writer."""

from __future__ import annotations

import sqlite3
from typing import cast

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments.models import (
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import (
    LeaseFence,
    SchedulerLease,
    SchedulerSlot,
)
from ditto_analysis.storage.sqlite.experiments._experiment_rules import (
    ACTIVE_EXPERIMENT_INTENT,
    TERMINAL_EXPERIMENT_STATUSES,
)
from ditto_analysis.storage.sqlite.experiments._scheduler_queue import (
    scheduler_queue_candidates,
    unowned_active_experiment,
)
from ditto_analysis.storage.sqlite.experiments._work_rules import (
    find_experiment_live_child,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)


def _persistence_error(message: str, reason_code: str) -> ExperimentPersistenceError:
    return ExperimentPersistenceError(message, details={"reason_code": reason_code})


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


def _lease_lost(message: str, reason_code: str) -> ExperimentLeaseLostError:
    return ExperimentLeaseLostError(message, details={"reason_code": reason_code})


def _validate_terminal_children_drained(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
    terminal_status: ExperimentStatus,
) -> None:
    live_child = find_experiment_live_child(
        connection,
        experiment_id,
        terminal_status,
    )
    if live_child is not None:
        raise ExperimentIntegrityError(
            "terminal scheduler occupant still has live child work",
            details={
                "reason_code": "scheduler_terminal_live_child",
                **live_child,
            },
        )


class SQLiteSchedulerLeaseMixin:
    """Provide revisioned singleton lease operations and downstream fencing."""

    _database: ResearchExperimentDatabase

    def try_claim_lease(
        self,
        experiment_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
        lease_until_epoch_us: int,
    ) -> SchedulerLease | None:
        self._validate_lease_inputs(owner_token, now_epoch_us, lease_until_epoch_us)
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._scheduler_row(connection)
            if row["revision"] != expected_revision:
                raise _lease_lost(
                    "scheduler revision is stale", "scheduler_lease_stale_revision"
                )
            if (
                row["owner_token"] is not None
                and row["lease_until_epoch_us"] > now_epoch_us
            ):
                connection.commit()
                return None
            if row["experiment_id"] is None:
                self._validate_queue_head(connection, experiment_id)
            else:
                self._validate_expired_occupant(
                    connection,
                    row["experiment_id"],
                    experiment_id,
                )
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_scheduler_slot
                SET experiment_id=?, owner_token=?, lease_until_epoch_us=?,
                    acquired_at_epoch_us=?, renewed_at_epoch_us=?, revision=?
                WHERE slot_id='global' AND revision=?
                  AND (owner_token IS NULL OR lease_until_epoch_us <= ?)
                """,
                (
                    str(experiment_id),
                    owner_token,
                    lease_until_epoch_us,
                    now_epoch_us,
                    now_epoch_us,
                    new_revision,
                    expected_revision,
                    now_epoch_us,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return None
            connection.commit()
            return SchedulerLease(
                experiment_id,
                owner_token,
                lease_until_epoch_us,
                now_epoch_us,
                now_epoch_us,
                new_revision,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "scheduler claim failed", "scheduler_claim_failed"
            ) from exc

    def renew_lease(
        self,
        fence: LeaseFence,
        *,
        now_epoch_us: int,
        new_lease_until_epoch_us: int,
    ) -> SchedulerLease:
        self._validate_lease_inputs(
            fence.owner_token, now_epoch_us, new_lease_until_epoch_us
        )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._validate_lease(
                connection, fence, now_epoch_us, fence.experiment_id
            )
            occupant = self._experiment_row(connection, fence.experiment_id)
            if ExperimentStatus(occupant["status"]) in TERMINAL_EXPERIMENT_STATUSES:
                raise ExperimentSpecError(
                    "terminal experiment cannot renew the scheduler lease",
                    details={"reason_code": "scheduler_renewal_not_allowed"},
                )
            self._validate_active_occupant_intent(occupant)
            new_revision = fence.revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_scheduler_slot
                SET lease_until_epoch_us=?, renewed_at_epoch_us=?, revision=?
                WHERE slot_id='global' AND experiment_id=? AND owner_token=?
                  AND revision=? AND lease_until_epoch_us=? AND lease_until_epoch_us > ?
                """,
                (
                    new_lease_until_epoch_us,
                    now_epoch_us,
                    new_revision,
                    str(fence.experiment_id),
                    fence.owner_token,
                    fence.revision,
                    fence.lease_until_epoch_us,
                    now_epoch_us,
                ),
            )
            if cursor.rowcount != 1:
                raise _lease_lost("scheduler renewal CAS lost", "scheduler_lease_lost")
            connection.commit()
            return SchedulerLease(
                fence.experiment_id,
                fence.owner_token,
                new_lease_until_epoch_us,
                row["acquired_at_epoch_us"],
                now_epoch_us,
                new_revision,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "scheduler renewal failed", "scheduler_renew_failed"
            ) from exc

    def release_lease(self, fence: LeaseFence, *, now_epoch_us: int) -> SchedulerSlot:
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(connection, fence, now_epoch_us, fence.experiment_id)
            occupant = self._experiment_row(connection, fence.experiment_id)
            occupant_status = ExperimentStatus(occupant["status"])
            if occupant_status not in TERMINAL_EXPERIMENT_STATUSES:
                if occupant_status not in ACTIVE_EXPERIMENT_INTENT:
                    raise _integrity(
                        "scheduler slot occupant has an invalid lifecycle",
                        "scheduler_invalid_occupant_lifecycle",
                    )
                raise ExperimentSpecError(
                    "active experiment must retain the scheduler slot",
                    details={"reason_code": "scheduler_release_not_allowed"},
                )
            _validate_terminal_children_drained(
                connection,
                fence.experiment_id,
                occupant_status,
            )
            new_revision = fence.revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment_scheduler_slot
                SET experiment_id=NULL, owner_token=NULL, lease_until_epoch_us=NULL,
                    acquired_at_epoch_us=NULL, renewed_at_epoch_us=NULL, revision=?
                WHERE slot_id='global' AND experiment_id=? AND owner_token=?
                  AND revision=? AND lease_until_epoch_us=? AND lease_until_epoch_us > ?
                """,
                (
                    new_revision,
                    str(fence.experiment_id),
                    fence.owner_token,
                    fence.revision,
                    fence.lease_until_epoch_us,
                    now_epoch_us,
                ),
            )
            if cursor.rowcount != 1:
                raise _lease_lost("scheduler release CAS lost", "scheduler_lease_lost")
            connection.commit()
            return SchedulerSlot("global", None, None, None, None, None, new_revision)
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "scheduler release failed", "scheduler_release_failed"
            ) from exc

    def handoff_lease(
        self,
        fence: LeaseFence,
        *,
        now_epoch_us: int,
    ) -> SchedulerSlot:
        """Expire active ownership while retaining the experiment's singleton slot."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            slot = self._validate_lease(
                connection,
                fence,
                now_epoch_us,
                fence.experiment_id,
            )
            occupant = self._experiment_row(connection, fence.experiment_id)
            self._validate_active_occupant_intent(occupant)
            new_revision = fence.revision + 1
            handoff_until_epoch_us = max(
                now_epoch_us,
                slot["renewed_at_epoch_us"] + 1,
            )
            cursor = connection.execute(
                """
                UPDATE experiment_scheduler_slot
                SET lease_until_epoch_us=?, revision=?
                WHERE slot_id='global' AND experiment_id=? AND owner_token=?
                  AND revision=? AND lease_until_epoch_us=?
                  AND lease_until_epoch_us > ?
                """,
                (
                    handoff_until_epoch_us,
                    new_revision,
                    str(fence.experiment_id),
                    fence.owner_token,
                    fence.revision,
                    fence.lease_until_epoch_us,
                    now_epoch_us,
                ),
            )
            if cursor.rowcount != 1:
                raise _lease_lost(
                    "scheduler handoff CAS lost",
                    "scheduler_lease_lost",
                )
            connection.commit()
            return SchedulerSlot(
                "global",
                fence.experiment_id,
                fence.owner_token,
                handoff_until_epoch_us,
                slot["acquired_at_epoch_us"],
                slot["renewed_at_epoch_us"],
                new_revision,
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "scheduler handoff failed",
                "scheduler_handoff_failed",
            ) from exc

    @staticmethod
    def _validate_lease_inputs(owner_token: str, now_epoch_us: int, until: int) -> None:
        raw_owner = cast("object", owner_token)
        if (
            not isinstance(raw_owner, str)
            or not owner_token.strip()
            or owner_token != owner_token.strip()
            or type(now_epoch_us) is not int
            or now_epoch_us < 0
            or type(until) is not int
            or until <= now_epoch_us
        ):
            raise ExperimentSpecError(
                "scheduler lease inputs are invalid",
                details={"reason_code": "invalid_scheduler_lease"},
            )

    @staticmethod
    def _scheduler_row(connection: sqlite3.Connection) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM experiment_scheduler_slot WHERE slot_id='global'"
        ).fetchone()
        if row is None:
            raise _integrity(
                "global scheduler slot is missing", "scheduler_slot_missing"
            )
        return row

    @staticmethod
    def _experiment_row(
        connection: sqlite3.Connection,
        experiment_id: ExperimentId | str,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT experiment_id, status, desired_state FROM experiment
            WHERE experiment_id=?
            """,
            (str(experiment_id),),
        ).fetchone()
        if row is None:
            raise _integrity(
                "scheduler experiment does not exist",
                "scheduler_occupant_not_found",
            )
        return row

    @staticmethod
    def _validate_active_occupant_intent(row: sqlite3.Row) -> None:
        status = ExperimentStatus(row["status"])
        desired_state = ExperimentDesiredState(row["desired_state"])
        expected_desired_state = ACTIVE_EXPERIMENT_INTENT.get(status)
        if expected_desired_state is None:
            raise _integrity(
                "scheduler slot occupant has an invalid lifecycle",
                "scheduler_invalid_occupant_lifecycle",
            )
        if desired_state is not expected_desired_state:
            raise ExperimentSpecError(
                "scheduler slot occupant intent disagrees with its lifecycle",
                details={
                    "reason_code": "scheduler_occupant_intent_mismatch",
                    "status": row["status"],
                    "desired_state": desired_state.value,
                    "expected_desired_state": expected_desired_state.value,
                },
            )

    @classmethod
    def _validate_queue_head(
        cls,
        connection: sqlite3.Connection,
        requested_experiment_id: ExperimentId,
    ) -> None:
        unowned_active = unowned_active_experiment(connection)
        if unowned_active is not None:
            raise _integrity(
                "active experiment exists without the singleton scheduler slot",
                "scheduler_active_experiment_without_slot",
            )
        candidates = scheduler_queue_candidates(connection)
        head = candidates[0] if candidates else None
        if head is None:
            requested = cls._experiment_row(connection, requested_experiment_id)
            raise ExperimentSpecError(
                "experiment is not eligible to claim the scheduler slot",
                details={
                    "reason_code": "scheduler_experiment_not_eligible",
                    "status": requested["status"],
                },
            )
        head_status = ExperimentStatus(head["status"])
        expected_desired_state = ACTIVE_EXPERIMENT_INTENT[head_status]
        if head["desired_state"] != expected_desired_state.value:
            raise ExperimentSpecError(
                "queue head intent does not permit scheduler dispatch",
                details={
                    "reason_code": "scheduler_queue_head_intent_mismatch",
                    "experiment_id": head["experiment_id"],
                    "desired_state": head["desired_state"],
                    "expected_desired_state": expected_desired_state.value,
                },
            )
        if head["experiment_id"] != str(requested_experiment_id):
            requested = cls._experiment_row(connection, requested_experiment_id)
            if not any(
                candidate["experiment_id"] == str(requested_experiment_id)
                for candidate in candidates
            ):
                raise ExperimentSpecError(
                    "experiment is not eligible to claim the scheduler slot",
                    details={
                        "reason_code": "scheduler_experiment_not_eligible",
                        "status": requested["status"],
                    },
                )
            raise ExperimentSpecError(
                "only the current queue head may claim the scheduler slot",
                details={
                    "reason_code": "scheduler_queue_order_violation",
                    "queue_head_experiment_id": head["experiment_id"],
                },
            )

    @classmethod
    def _validate_expired_occupant(
        cls,
        connection: sqlite3.Connection,
        occupant_experiment_id: str,
        requested_experiment_id: ExperimentId,
    ) -> None:
        occupant = cls._experiment_row(connection, occupant_experiment_id)
        occupant_status = ExperimentStatus(occupant["status"])
        if occupant_status in ACTIVE_EXPERIMENT_INTENT:
            cls._validate_active_occupant_intent(occupant)
            if occupant_experiment_id != str(requested_experiment_id):
                raise ExperimentSpecError(
                    "expired active scheduler slot must be reclaimed in place",
                    details={
                        "reason_code": "scheduler_reclaim_required",
                        "experiment_id": occupant_experiment_id,
                    },
                )
            return
        if occupant_status in TERMINAL_EXPERIMENT_STATUSES:
            _validate_terminal_children_drained(
                connection,
                ExperimentId(occupant_experiment_id),
                occupant_status,
            )
            cls._validate_queue_head(connection, requested_experiment_id)
            return
        raise _integrity(
            "scheduler slot occupant has an invalid lifecycle",
            "scheduler_invalid_occupant_lifecycle",
        )

    @classmethod
    def _validate_lease(
        cls,
        connection: sqlite3.Connection,
        fence: LeaseFence,
        now_epoch_us: int,
        expected_experiment_id: ExperimentId,
    ) -> sqlite3.Row:
        row = cls._scheduler_row(connection)
        if fence.experiment_id != expected_experiment_id or row["experiment_id"] != str(
            expected_experiment_id
        ):
            raise _lease_lost(
                "scheduler lease belongs to another experiment",
                "scheduler_lease_foreign_experiment",
            )
        if row["lease_until_epoch_us"] <= now_epoch_us:
            raise _lease_lost("scheduler lease has expired", "scheduler_lease_expired")
        if (
            row["owner_token"] != fence.owner_token
            or row["revision"] != fence.revision
            or row["lease_until_epoch_us"] != fence.lease_until_epoch_us
        ):
            raise _lease_lost(
                "scheduler fencing token is stale", "scheduler_lease_lost"
            )
        return row
