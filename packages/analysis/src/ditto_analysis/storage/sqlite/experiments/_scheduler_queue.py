"""Shared scheduler queue classification over durable lifecycle events."""

from __future__ import annotations

import sqlite3

from ditto_analysis.experiments.models import ExperimentStatus

_UNSLOTTED_ACTIVE_STATUSES = frozenset(
    {
        ExperimentStatus.RUNNING,
        ExperimentStatus.PAUSE_REQUESTED,
        ExperimentStatus.PAUSED,
    }
)


def _active_queue_rows(connection: sqlite3.Connection) -> tuple[sqlite3.Row, ...]:
    return tuple(
        connection.execute(
            """
            SELECT experiment.*,
                   event.previous_status AS latest_previous_status,
                   event.status AS latest_event_status,
                   event.desired_state AS latest_event_desired_state
            FROM experiment
            LEFT JOIN experiment_status_event AS event
              ON event.experiment_id=experiment.experiment_id
             AND event.subject_type='experiment'
             AND event.subject_revision=experiment.revision
            WHERE experiment.status IN (
                'queued', 'running', 'pause_requested', 'paused',
                'cancel_requested'
            )
            ORDER BY experiment.queue_ordinal, experiment.experiment_id
            """
        ).fetchall()
    )


def _is_queued_origin_cancel(row: sqlite3.Row) -> bool:
    return (
        row["status"] == ExperimentStatus.CANCEL_REQUESTED.value
        and row["latest_previous_status"] == ExperimentStatus.QUEUED.value
        and row["latest_event_status"] == ExperimentStatus.CANCEL_REQUESTED.value
        and row["latest_event_desired_state"] == "cancel"
    )


def scheduler_queue_candidates(
    connection: sqlite3.Connection,
) -> tuple[sqlite3.Row, ...]:
    """Return queued work and queued-origin cancellation drains in stable order."""
    return tuple(
        row
        for row in _active_queue_rows(connection)
        if row["status"] == ExperimentStatus.QUEUED.value
        or _is_queued_origin_cancel(row)
    )


def unowned_active_experiment(connection: sqlite3.Connection) -> sqlite3.Row | None:
    """Find active work that cannot legitimately wait in the scheduler queue."""
    return next(
        (
            row
            for row in _active_queue_rows(connection)
            if ExperimentStatus(row["status"]) in _UNSLOTTED_ACTIVE_STATUSES
            or (
                row["status"] == ExperimentStatus.CANCEL_REQUESTED.value
                and not _is_queued_origin_cancel(row)
            )
        ),
        None,
    )
