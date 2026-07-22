"""Append-only artifact, gate, and holdout commands for experiment storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    GateEvaluationRecord,
    LeaseFence,
    canonical_payload,
    validate_artifact_relative_path,
)
from ditto_analysis.storage.sqlite.experiments._lease import SQLiteSchedulerLeaseMixin
from ditto_analysis.storage.sqlite.experiments.reader import SQLiteExperimentReader


def _epoch_us(value: datetime) -> int:
    require_utc_datetime(value, "datetime")
    return int(value.timestamp() * 1_000_000)


def _optional(value: object | None) -> str | None:
    return None if value is None else str(value)


def _json_text(value: Mapping[str, object] | object) -> str:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return canonical_payload(mapping).json_bytes.decode("utf-8")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _persistence_error(message: str, reason_code: str) -> ExperimentPersistenceError:
    return ExperimentPersistenceError(message, details={"reason_code": reason_code})


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


def _conflict(message: str, reason_code: str) -> ExperimentConflictError:
    return ExperimentConflictError(message, details={"reason_code": reason_code})


class SQLiteExperimentFactsMixin(SQLiteSchedulerLeaseMixin):
    """Persist immutable artifacts and gate evaluations."""

    _reader: SQLiteExperimentReader

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> None:
        path = validate_artifact_relative_path(record.relative_path)
        artifact_root = (self._database.path.parent / "artifacts").resolve()
        candidate_path = (artifact_root / Path(*path.parts)).resolve()
        if not candidate_path.is_relative_to(artifact_root):
            raise ExperimentSpecError(
                "artifact path escapes the canonical artifact root",
                details={"reason_code": "invalid_artifact_relative_path"},
            )
        manifest = canonical_payload(record.manifest)
        values = (
            record.artifact_id,
            str(record.experiment_id),
            _optional(record.candidate_id),
            _optional(record.fold_id),
            _optional(record.attempt_id),
            record.artifact_kind,
            record.relative_path,
            str(record.content_hash),
            str(record.schema_hash),
            record.row_count,
            record.byte_size,
            str(record.reproduction_fingerprint),
            manifest.json_bytes.decode("utf-8"),
            int(record.is_pinned),
            None if record.pinned_at is None else _epoch_us(record.pinned_at),
            _epoch_us(record.created_at),
            record.revision,
        )
        if record.is_pinned or record.pinned_at is not None or record.revision != 0:
            raise ExperimentSpecError(
                "new artifact must be unpinned at revision zero",
                details={"reason_code": "invalid_initial_artifact_projection"},
            )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM research_artifact WHERE artifact_id=?",
                (record.artifact_id,),
            ).fetchone()
            if existing is not None:
                immutable_indexes = (*range(13), 15)
                if tuple(existing[index] for index in immutable_indexes) != tuple(
                    values[index] for index in immutable_indexes
                ):
                    raise _conflict("artifact replay drift", "artifact_replay_drift")
                connection.commit()
                return
            self._validate_lease(
                connection, lease_fence, now_epoch_us, record.experiment_id
            )
            connection.execute(
                """
                INSERT INTO research_artifact(
                    artifact_id, experiment_id, candidate_id, fold_id, attempt_id,
                    artifact_kind, relative_path, content_hash, schema_hash, row_count,
                    byte_size, reproduction_fingerprint, manifest_json, is_pinned,
                    pinned_at_epoch_us, created_at_epoch_us, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            connection.commit()
        except (
            ExperimentConflictError,
            ExperimentIntegrityError,
            ExperimentLeaseLostError,
        ):
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise _integrity(
                "artifact lineage is invalid", "invalid_artifact_lineage"
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "artifact insert failed", "artifact_insert_failed"
            ) from exc

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
    ) -> ArtifactRecord:
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM research_artifact WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if row is None:
                raise _integrity("artifact does not exist", "artifact_not_found")
            if row["revision"] != expected_revision or row["is_pinned"]:
                raise _conflict(
                    "artifact pin revision is stale", "stale_artifact_revision"
                )
            cursor = connection.execute(
                """
                UPDATE research_artifact
                SET is_pinned=1, pinned_at_epoch_us=?, revision=?
                WHERE artifact_id=? AND revision=? AND is_pinned=0
                """,
                (
                    _epoch_us(pinned_at),
                    expected_revision + 1,
                    artifact_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("artifact pin CAS lost", "stale_artifact_revision")
            connection.commit()
            result = self._reader.get_artifact(artifact_id)
            if result is None:
                raise _integrity(
                    "artifact disappeared after its pin transaction",
                    "artifact_not_found_after_pin",
                )
            return result
        except (ExperimentConflictError, ExperimentIntegrityError):
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "artifact pin failed", "artifact_pin_failed"
            ) from exc

    def add_gate_evaluation(self, record: GateEvaluationRecord) -> None:
        values = (
            record.evaluation_id,
            str(record.experiment_id),
            _optional(record.candidate_id),
            _optional(record.fold_id),
            _optional(record.attempt_id),
            record.rule_id,
            record.policy_version,
            record.layer,
            record.outcome,
            _json_text(record.observed),
            _json_text(record.policy),
            record.artifact_id,
            str(record.payload_hash),
            _epoch_us(record.evaluated_at),
        )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM gate_evaluation WHERE evaluation_id=?",
                (record.evaluation_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != values:
                    raise _conflict(
                        "gate evaluation replay drift",
                        "gate_evaluation_replay_drift",
                    )
                connection.commit()
                return
            connection.execute(
                """
                INSERT INTO gate_evaluation(
                    evaluation_id, experiment_id, candidate_id, fold_id, attempt_id,
                    rule_id, policy_version, layer, outcome, observed_json,
                    policy_json, artifact_id, payload_hash, evaluated_at_epoch_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            connection.commit()
        except ExperimentConflictError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise _integrity(
                "gate evaluation lineage is invalid",
                "invalid_gate_evaluation_lineage",
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "gate evaluation insert failed",
                "gate_evaluation_insert_failed",
            ) from exc
