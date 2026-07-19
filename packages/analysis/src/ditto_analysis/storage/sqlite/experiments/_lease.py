"""Singleton scheduler lease commands shared by the experiment writer."""

from __future__ import annotations

import sqlite3
from typing import cast

from ditto_analysis.errors import (
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments.models import ExperimentId
from ditto_analysis.experiments.persistence import (
    LeaseFence,
    SchedulerLease,
    SchedulerSlot,
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
        except ExperimentLeaseLostError:
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
        except ExperimentLeaseLostError:
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
        except ExperimentLeaseLostError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "scheduler release failed", "scheduler_release_failed"
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
