"""
Artifact read helpers composed by :class:`SQLiteExperimentReader`.

Kept in a leaf submodule so the reader stays under the file-size budget; the
reader delegates to these pure read functions, passing its bounded fetch
helpers so SQLite error wrapping stays in one place.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import cast

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments._time import datetime_from_epoch_us as _dt
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import ArtifactRecord

__all__ = ["artifact_record", "fetch_experiment_artifacts"]


def _json_object(payload: str, field: str) -> dict[str, object]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ExperimentIntegrityError(
            f"persisted {field} is not JSON",
            details={"reason_code": "persisted_payload_invalid", "field": field},
        ) from exc
    if not isinstance(decoded, dict):
        raise ExperimentIntegrityError(
            f"persisted {field} is not an object",
            details={"reason_code": "persisted_payload_invalid", "field": field},
        )
    return cast("dict[str, object]", decoded)


def artifact_record(row: sqlite3.Row) -> ArtifactRecord:
    """Project one immutable ``research_artifact`` row into the typed record."""
    return ArtifactRecord(
        artifact_id=row["artifact_id"],
        experiment_id=ExperimentId(row["experiment_id"]),
        candidate_id=(
            None if row["candidate_id"] is None else CandidateId(row["candidate_id"])
        ),
        fold_id=None if row["fold_id"] is None else FoldId(row["fold_id"]),
        attempt_id=(
            None if row["attempt_id"] is None else AttemptId(row["attempt_id"])
        ),
        artifact_kind=row["artifact_kind"],
        relative_path=row["relative_path"],
        content_hash=ContentHash(row["content_hash"]),
        schema_hash=ContentHash(row["schema_hash"]),
        row_count=row["row_count"],
        byte_size=row["byte_size"],
        reproduction_fingerprint=ContentHash(row["reproduction_fingerprint"]),
        manifest=_json_object(row["manifest_json"], "manifest_json"),
        is_pinned=bool(row["is_pinned"]),
        pinned_at=(
            None
            if row["pinned_at_epoch_us"] is None
            else _dt(row["pinned_at_epoch_us"])
        ),
        created_at=_dt(row["created_at_epoch_us"]),
        revision=row["revision"],
    )


def fetch_experiment_artifacts(
    fetchall: Callable[[str, tuple[object, ...]], list[sqlite3.Row]],
    experiment_id: ExperimentId,
) -> tuple[ArtifactRecord, ...]:
    """List every indexed artifact for one experiment in stable lineage order."""
    rows = fetchall(
        """
        SELECT * FROM research_artifact
        WHERE experiment_id=?
        ORDER BY candidate_id, fold_id, attempt_id, artifact_kind,
                 created_at_epoch_us
        """,
        (str(experiment_id),),
    )
    return tuple(artifact_record(row) for row in rows)
