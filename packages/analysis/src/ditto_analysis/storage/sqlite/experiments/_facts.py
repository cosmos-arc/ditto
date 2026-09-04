"""Append-only artifact, gate, and holdout commands for experiment storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
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
from ditto_analysis.experiments._time import epoch_us
from ditto_analysis.experiments.models import (
    CandidateId,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    ExperimentProjection,
    GateEvaluationRecord,
    LeaseFence,
    canonical_payload,
    validate_artifact_relative_path,
)
from ditto_analysis.storage.sqlite.experiments._lease import SQLiteSchedulerLeaseMixin
from ditto_analysis.storage.sqlite.experiments._writer_reader_port import (
    SQLiteExperimentWriterReaderState,
)

#: Artifact kinds produced after the scheduler lease has released; their
#: integrity is anchored by content-addressed hashes, not in-flight lease state.
_LEASE_EXEMPT_KINDS = frozenset({"review_packet"})


def _epoch_us(value: datetime) -> int:
    return epoch_us(value)


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


class SQLiteExperimentFactsMixin(
    SQLiteSchedulerLeaseMixin,
    SQLiteExperimentWriterReaderState,
):
    """Persist immutable artifacts and gate evaluations."""

    _insert_event: Callable[..., None]

    @property
    def artifact_root(self) -> Path:
        """Expose the database-owned canonical root to verified file I/O."""
        return self._database.artifact_root

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        validate_artifact_relative_path(record.relative_path)
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
            matches = connection.execute(
                """
                SELECT * FROM research_artifact
                WHERE artifact_id=? OR relative_path=?
                ORDER BY artifact_id
                """,
                (record.artifact_id, record.relative_path),
            ).fetchall()
            if len(matches) > 1:
                raise _conflict(
                    "artifact identity and path resolve to different facts",
                    "artifact_identity_cross_conflict",
                )
            if matches:
                existing = matches[0]
                if (
                    existing["artifact_id"] != record.artifact_id
                    or existing["relative_path"] != record.relative_path
                ):
                    raise _conflict(
                        "artifact path is bound to another identity",
                        "artifact_path_identity_conflict",
                    )
                immutable_indexes = (*range(13), 15)
                if tuple(existing[index] for index in immutable_indexes) != tuple(
                    values[index] for index in immutable_indexes
                ):
                    raise _conflict("artifact replay drift", "artifact_replay_drift")
                commit_guard()
                connection.commit()
                return
            self._enforce_lease_if_required(
                connection, record, lease_fence, now_epoch_us
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
            commit_guard()
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
        except BaseException:
            connection.rollback()
            raise

    def _enforce_lease_if_required(
        self,
        connection: sqlite3.Connection,
        record: ArtifactRecord,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> None:
        """Enforce the scheduler lease unless the artifact kind is exempt."""
        if record.artifact_kind not in _LEASE_EXEMPT_KINDS:
            self._validate_lease(
                connection, lease_fence, now_epoch_us, record.experiment_id
            )

    def record_candidate_selection(
        self,
        experiment_id: ExperimentId,
        candidate_id: CandidateId,
        *,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object],
    ) -> ExperimentProjection:
        """Append one revision-fenced preselection event without a new table."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_lease(
                connection,
                lease_fence,
                now_epoch_us,
                experiment_id,
            )
            row = connection.execute(
                "SELECT * FROM experiment WHERE experiment_id=?",
                (str(experiment_id),),
            ).fetchone()
            if row is None:
                raise _integrity("experiment does not exist", "experiment_not_found")
            if row["revision"] != expected_revision:
                raise _conflict(
                    "candidate selection revision is stale",
                    "stale_projection_revision",
                )
            if (
                row["status"] != ExperimentStatus.RUNNING.value
                or row["desired_state"] != ExperimentDesiredState.RUN.value
                or row["stage"] != ExperimentStage.CANDIDATE_SELECTION.value
                or row["failure_code"] is not None
            ):
                raise ExperimentSpecError(
                    "candidate selection requires the live candidate-selection stage",
                    details={"reason_code": "candidate_selection_stage_invalid"},
                )
            candidate = connection.execute(
                """
                SELECT is_baseline FROM experiment_candidate
                WHERE experiment_id=? AND candidate_id=?
                """,
                (str(experiment_id), str(candidate_id)),
            ).fetchone()
            if candidate is None or candidate["is_baseline"]:
                raise ExperimentSpecError(
                    "candidate is not eligible for preselection",
                    details={"reason_code": "candidate_not_eligible"},
                )
            existing = connection.execute(
                """
                SELECT event_id FROM experiment_status_event
                WHERE experiment_id=? AND reason_code='candidate_preselected'
                """,
                (str(experiment_id),),
            ).fetchall()
            if existing:
                raise _conflict(
                    "candidate preselection already exists",
                    "candidate_selection_conflict",
                )
            new_revision = expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment
                SET updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND revision=? AND status='running'
                  AND desired_state='run' AND stage='candidate_selection'
                """,
                (
                    _epoch_us(occurred_at),
                    new_revision,
                    str(experiment_id),
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict(
                    "candidate selection CAS lost",
                    "stale_projection_revision",
                )
            self._insert_event(
                connection,
                subject_type="experiment",
                experiment_id=str(experiment_id),
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                revision=new_revision,
                previous_status=ExperimentStatus.RUNNING,
                status=ExperimentStatus.RUNNING,
                desired_state=ExperimentDesiredState.RUN,
                stage=ExperimentStage.CANDIDATE_SELECTION,
                failure_code=None,
                reason_code="candidate_preselected",
                detail=detail,
                occurred_at=occurred_at,
            )
            connection.commit()
            return ExperimentProjection(
                ExperimentRecord(
                    experiment_id,
                    ExperimentStatus.RUNNING,
                    ExperimentDesiredState.RUN,
                    ExperimentStage.CANDIDATE_SELECTION,
                    datetime.fromtimestamp(
                        row["created_at_epoch_us"] / 1_000_000,
                        tz=occurred_at.tzinfo,
                    ),
                ),
                row["queue_ordinal"],
                new_revision,
                occurred_at,
            )
        except (
            ExperimentConflictError,
            ExperimentIntegrityError,
            ExperimentLeaseLostError,
            ExperimentSpecError,
        ):
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "candidate selection event failed",
                "candidate_selection_event_failed",
            ) from exc

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
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
            commit_guard()
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
        except BaseException:
            connection.rollback()
            raise

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
