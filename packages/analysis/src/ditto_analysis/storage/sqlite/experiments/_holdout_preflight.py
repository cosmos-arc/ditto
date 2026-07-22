"""Canonical preflight authority validation for sealed holdout access."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import cast

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments.models import (
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import canonical_payload
from ditto_analysis.storage.sqlite.experiments._events import (
    canonical_status_event_id,
)


def _integrity(message: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": "holdout_preflight_authority_invalid"},
    )


def validate_holdout_preflight(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
) -> None:
    """Require one hash-verified ready preflight event with RUN semantics."""
    events = connection.execute(
        """
        SELECT * FROM experiment_status_event
        WHERE experiment_id=? AND subject_type='experiment'
          AND reason_code='preflight_passed'
        ORDER BY subject_revision, event_id
        """,
        (str(experiment_id),),
    ).fetchall()
    if len(events) != 1:
        raise _integrity("canonical preflight authority is missing or ambiguous")
    event = events[0]
    try:
        detail = json.loads(event["detail_json"])
    except json.JSONDecodeError as exc:
        raise _integrity("preflight authority payload is invalid") from exc
    if not isinstance(detail, dict):
        raise _integrity("preflight authority payload is not an object")
    detail_mapping = cast("Mapping[str, object]", detail)
    canonical = canonical_payload(detail_mapping)
    preflight = detail_mapping.get("preflight")
    preflight_mapping = (
        cast("Mapping[str, object]", preflight) if isinstance(preflight, dict) else None
    )
    canonical_event_id = canonical_status_event_id(
        subject_type="experiment",
        experiment_id=str(experiment_id),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        revision=event["subject_revision"],
    )
    if (
        canonical.json_bytes.decode("utf-8") != event["detail_json"]
        or str(canonical.content_hash) != event["detail_hash"]
        or event["event_id"] != canonical_event_id
        or event["previous_status"]
        not in {ExperimentStatus.DRAFT.value, ExperimentStatus.BLOCKED.value}
        or event["status"] != ExperimentStatus.QUEUED.value
        or event["desired_state"] != ExperimentDesiredState.RUN.value
        or event["stage"] != ExperimentStage.PREFLIGHT.value
        or event["failure_code"] is not None
        or preflight_mapping is None
        or preflight_mapping.get("status") != "ready"
    ):
        raise _integrity("preflight authority is absent, restricted, or drifted")
