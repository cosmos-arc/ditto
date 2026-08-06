"""Canonical status-event encoding shared by writers and readers."""

# Command fields stay explicit at this persistence boundary.
# ruff: noqa: PLR0913

from __future__ import annotations

from collections.abc import Mapping

from ditto_analysis.experiments.models import (
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import canonical_payload


def _optional(value: object | None) -> str | None:
    return None if value is None else str(value)


def canonical_status_event_id(
    *,
    subject_type: str,
    experiment_id: str,
    candidate_id: str | None,
    fold_id: str | None,
    attempt_id: str | None,
    revision: int,
) -> str:
    """Derive the canonical event identity from typed lineage and revision."""
    identity = canonical_payload(
        {
            "attempt_id": attempt_id,
            "candidate_id": candidate_id,
            "experiment_id": experiment_id,
            "fold_id": fold_id,
            "revision": revision,
            "subject_type": subject_type,
        }
    )
    return f"status:{identity.content_hash}"


def event_values(
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
    occurred_at_epoch_us: int,
) -> tuple[object, ...]:
    """Encode a complete canonical status-event row."""
    payload = canonical_payload(detail)
    event_id = canonical_status_event_id(
        subject_type=subject_type,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        fold_id=fold_id,
        attempt_id=attempt_id,
        revision=revision,
    )
    return (
        event_id,
        experiment_id,
        candidate_id,
        fold_id,
        attempt_id,
        subject_type,
        revision,
        _optional(previous_status),
        status.value,
        _optional(desired_state),
        _optional(stage),
        _optional(failure_code),
        reason_code,
        payload.json_bytes.decode("utf-8"),
        str(payload.content_hash),
        occurred_at_epoch_us,
    )
