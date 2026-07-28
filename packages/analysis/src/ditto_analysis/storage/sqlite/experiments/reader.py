"""Typed, lossless reader for the experiment control-plane schema."""

# The public read verbs are fully typed by the analysis-owned persistence contracts.
# ruff: noqa: D102

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import cast

from ditto_analysis.errors import (
    ExperimentIntegrityError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments._time import datetime_from_epoch_us as _dt
from ditto_analysis.experiments._time import epoch_us
from ditto_analysis.experiments.evidence import (
    ReviewPacket,
    review_packet_from_payload,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    BacktestRunId,
    CandidateId,
    CheckpointRef,
    ContentHash,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    DateWindow,
    ExperimentProjection,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
    GateEvaluationRecord,
    HoldoutClaimRecord,
    ResearchCycleIdentity,
    SchedulerSlot,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
    decode_launch_spec,
    encode_candidate_parameters,
    encode_launch_spec,
)
from ditto_analysis.experiments.specs import (
    CandidateSpec,
    ExperimentLaunchSpec,
    FrozenValue,
)
from ditto_analysis.storage.sqlite.experiments._events import (
    canonical_status_event_id,
    event_values,
)
from ditto_analysis.storage.sqlite.experiments._holdout import (
    holdout_claim_from_row,
)
from ditto_analysis.storage.sqlite.experiments._scheduler_queue import (
    scheduler_queue_candidates,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)


def _integrity(
    message: str, reason_code: str, **details: object
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _failure(value: str | None) -> ExperimentFailureCode | None:
    return None if value is None else ExperimentFailureCode(value)


def _json_object(payload: str, field: str) -> dict[str, object]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise _integrity(
            f"persisted {field} is not JSON",
            "persisted_payload_invalid",
            field=field,
        ) from exc
    if not isinstance(decoded, dict):
        raise _integrity(
            f"persisted {field} is not an object",
            "persisted_payload_invalid",
            field=field,
        )
    return cast("dict[str, object]", decoded)


class SQLiteExperimentReader:
    """Read approved experiment records without exposing SQLite rows."""

    def __init__(self, database: ResearchExperimentDatabase) -> None:
        self._database = database

    @property
    def artifact_root(self) -> Path:
        """Expose the database-owned canonical root to the composed file service."""
        return self._database.artifact_root

    def _one(self, sql: str, parameters: tuple[object, ...]) -> sqlite3.Row | None:
        try:
            return self._database.get_connection().execute(sql, parameters).fetchone()
        except sqlite3.Error as exc:
            raise ExperimentPersistenceError(
                "experiment read failed",
                details={"reason_code": "experiment_read_failed"},
            ) from exc

    def get_research_cycle_identity(
        self, experiment_id: ExperimentId
    ) -> ResearchCycleIdentity | None:
        row = self._one(
            """
            SELECT research_cycle_id, research_cycle_hash
            FROM experiment WHERE experiment_id=?
            """,
            (str(experiment_id),),
        )
        if row is None:
            return None
        return ResearchCycleIdentity(
            row["research_cycle_id"], ContentHash(row["research_cycle_hash"])
        )

    def get_launch_spec(
        self, experiment_id: ExperimentId
    ) -> ExperimentLaunchSpec | None:
        row = self._one(
            "SELECT * FROM experiment WHERE experiment_id=?", (str(experiment_id),)
        )
        if row is None:
            return None
        spec = decode_launch_spec(
            row["launch_spec_json"].encode("utf-8"),
            ContentHash(row["launch_spec_hash"]),
        )
        canonical_launch = encode_launch_spec(spec)
        if row["launch_spec_schema_version"] != canonical_launch.schema_version:
            raise _integrity(
                "relational launch schema version disagrees with its payload",
                "launch_schema_version_mismatch",
                experiment_id=str(experiment_id),
            )
        if (
            spec.experiment_id != experiment_id
            or str(spec.strategy_version) != row["strategy_version"]
            or str(spec.strategy_spec_hash) != row["strategy_spec_hash"]
            or str(spec.snapshot_id) != row["snapshot_id"]
            or epoch_us(spec.created_at) != row["created_at_epoch_us"]
        ):
            raise _integrity(
                "launch payload disagrees with immutable relational fields",
                "launch_projection_drift",
                experiment_id=str(experiment_id),
            )
        expected_creation = event_values(
            subject_type="experiment",
            experiment_id=str(experiment_id),
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            revision=0,
            previous_status=None,
            status=ExperimentStatus.DRAFT,
            desired_state=spec.desired_state,
            stage=ExperimentStage.PREFLIGHT,
            failure_code=None,
            reason_code="experiment_created",
            detail={},
            occurred_at_epoch_us=epoch_us(spec.created_at),
        )
        creation = self._one(
            """
            SELECT * FROM experiment_status_event
            WHERE experiment_id=? AND subject_type='experiment'
              AND subject_revision=0
            """,
            (str(experiment_id),),
        )
        if creation is None or tuple(creation) != expected_creation:
            raise _integrity(
                "launch creation event is missing or drifted",
                "launch_creation_event_drift",
                experiment_id=str(experiment_id),
            )
        persisted_candidates = self.list_candidates(experiment_id)
        if persisted_candidates != tuple(spec.candidates):
            raise _integrity(
                "launch payload disagrees with relational candidates",
                "launch_candidate_drift",
                experiment_id=str(experiment_id),
            )
        return spec

    def get_experiment_projection(
        self, experiment_id: ExperimentId
    ) -> ExperimentProjection | None:
        row = self._one(
            "SELECT * FROM experiment WHERE experiment_id=?", (str(experiment_id),)
        )
        if row is None:
            return None
        return self._experiment_projection(row)

    @staticmethod
    def _experiment_projection(row: sqlite3.Row) -> ExperimentProjection:
        record = ExperimentRecord(
            experiment_id=ExperimentId(row["experiment_id"]),
            status=ExperimentStatus(row["status"]),
            desired_state=ExperimentDesiredState(row["desired_state"]),
            stage=ExperimentStage(row["stage"]),
            created_at=_dt(row["created_at_epoch_us"]),
            failure_code=_failure(row["failure_code"]),
        )
        return ExperimentProjection(
            record=record,
            queue_ordinal=row["queue_ordinal"],
            revision=row["revision"],
            updated_at=_dt(row["updated_at_epoch_us"]),
        )

    def list_dispatchable_experiments(self) -> tuple[ExperimentProjection, ...]:
        rows = scheduler_queue_candidates(self._database.get_connection())
        return tuple(self._experiment_projection(row) for row in rows)

    def list_experiments(self) -> tuple[ExperimentProjection, ...]:
        """List every experiment projection, newest first."""
        rows = (
            self._database.get_connection()
            .execute("SELECT * FROM experiment ORDER BY created_at_epoch_us DESC")
            .fetchall()
        )
        return tuple(self._experiment_projection(row) for row in rows)

    def list_candidates(self, experiment_id: ExperimentId) -> tuple[CandidateSpec, ...]:
        rows = (
            self._database.get_connection()
            .execute(
                """
                SELECT * FROM experiment_candidate
                WHERE experiment_id=? ORDER BY ordinal, candidate_id
                """,
                (str(experiment_id),),
            )
            .fetchall()
        )
        candidates: list[CandidateSpec] = []
        for row in rows:
            parameters = _json_object(row["parameters_json"], "parameters_json")
            try:
                candidate = CandidateSpec(
                    candidate_id=CandidateId(row["candidate_id"]),
                    ordinal=row["ordinal"],
                    is_baseline=bool(row["is_baseline"]),
                    parameters=cast("Mapping[str, FrozenValue]", parameters),
                )
            except ExperimentSpecError as exc:
                raise _integrity(
                    "persisted candidate parameters are invalid",
                    "persisted_candidate_parameters_invalid",
                    candidate_id=row["candidate_id"],
                ) from exc
            encoded = encode_candidate_parameters(candidate.parameters)
            if str(encoded.content_hash) != row["parameters_hash"]:
                raise _integrity(
                    "candidate parameter hash mismatch",
                    "candidate_parameter_hash_mismatch",
                    candidate_id=row["candidate_id"],
                )
            candidates.append(candidate)
        return tuple(candidates)

    def get_fold(self, key: FoldKey) -> FoldView | None:
        row = self._one(
            """
            SELECT * FROM experiment_fold
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            """,
            (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
        )
        return None if row is None else self._fold_view(row)

    def list_folds(self, experiment_id: ExperimentId) -> tuple[FoldView, ...]:
        rows = (
            self._database.get_connection()
            .execute(
                """
            SELECT * FROM experiment_fold WHERE experiment_id=?
            ORDER BY ordinal, candidate_id, fold_id
            """,
                (str(experiment_id),),
            )
            .fetchall()
        )
        return tuple(self._fold_view(row) for row in rows)

    def list_claimable_folds(self, experiment_id: ExperimentId) -> tuple[FoldView, ...]:
        rows = (
            self._database.get_connection()
            .execute(
                """
                SELECT fold.*
                FROM experiment_fold AS fold
                JOIN experiment_candidate AS candidate
                  ON candidate.experiment_id = fold.experiment_id
                 AND candidate.candidate_id = fold.candidate_id
                WHERE fold.experiment_id=? AND fold.status='queued'
                ORDER BY candidate.ordinal, fold.ordinal, fold.fold_id
                """,
                (str(experiment_id),),
            )
            .fetchall()
        )
        return tuple(self._fold_view(row) for row in rows)

    @staticmethod
    def _fold_view(row: sqlite3.Row) -> FoldView:
        payload = row["fold_spec_json"].encode("utf-8")
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != row["fold_spec_hash"]:
            raise _integrity(
                "fold canonical payload hash mismatch",
                "fold_payload_hash_mismatch",
                fold_id=row["fold_id"],
            )
        key = FoldKey(
            ExperimentId(row["experiment_id"]),
            CandidateId(row["candidate_id"]),
            FoldId(row["fold_id"]),
        )
        train_window = (
            None
            if row["train_start"] is None
            else DateWindow(
                date.fromisoformat(row["train_start"]),
                date.fromisoformat(row["train_end"]),
            )
        )
        spec = FoldPersistenceSpec(
            key=key,
            ordinal=row["ordinal"],
            fold_role=FoldRole(row["fold_role"]),
            train_window=train_window,
            test_window=DateWindow(
                date.fromisoformat(row["test_start"]),
                date.fromisoformat(row["test_end"]),
            ),
            purge_sessions=row["purge_sessions"],
            embargo_sessions=row["embargo_sessions"],
            canonical_payload=payload,
            payload_hash=ContentHash(row["fold_spec_hash"]),
        )
        expected = FoldPersistenceSpec.create(
            key=spec.key,
            ordinal=spec.ordinal,
            fold_role=spec.fold_role,
            train_window=spec.train_window,
            test_window=spec.test_window,
            purge_sessions=spec.purge_sessions,
            embargo_sessions=spec.embargo_sessions,
        )
        if expected.canonical_payload != spec.canonical_payload:
            raise _integrity(
                "fold payload disagrees with its relational fields",
                "fold_relation_payload_mismatch",
                fold_id=row["fold_id"],
            )
        projection = FoldProjection(
            key=key,
            status=ExperimentStatus(row["status"]),
            claim_owner_token=row["claim_owner_token"],
            created_at=_dt(row["created_at_epoch_us"]),
            updated_at=_dt(row["updated_at_epoch_us"]),
            revision=row["revision"],
        )
        return FoldView(spec, projection)

    def get_attempt(self, attempt_id: AttemptId) -> AttemptView | None:
        row = self._one(
            "SELECT * FROM experiment_attempt WHERE attempt_id=?",
            (str(attempt_id),),
        )
        return None if row is None else self._attempt_view(row)

    def list_attempts(self, key: FoldKey) -> tuple[AttemptView, ...]:
        rows = (
            self._database.get_connection()
            .execute(
                """
            SELECT * FROM experiment_attempt
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            ORDER BY ordinal, attempt_id
            """,
                (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
            )
            .fetchall()
        )
        return tuple(self._attempt_view(row) for row in rows)

    def list_experiment_attempts(
        self, experiment_id: ExperimentId
    ) -> tuple[AttemptView, ...]:
        rows = (
            self._database.get_connection()
            .execute(
                """
                SELECT attempt.*
                FROM experiment_attempt AS attempt
                LEFT JOIN experiment_fold AS fold
                  ON fold.experiment_id = attempt.experiment_id
                 AND fold.candidate_id = attempt.candidate_id
                 AND fold.fold_id = attempt.fold_id
                WHERE attempt.experiment_id=?
                ORDER BY
                    fold.ordinal,
                    fold.candidate_id,
                    fold.fold_id,
                    attempt.ordinal,
                    attempt.attempt_id
                """,
                (str(experiment_id),),
            )
            .fetchall()
        )
        return tuple(self._attempt_view(row) for row in rows)

    @staticmethod
    def _attempt_view(row: sqlite3.Row) -> AttemptView:
        key = FoldKey(
            ExperimentId(row["experiment_id"]),
            CandidateId(row["candidate_id"]),
            FoldId(row["fold_id"]),
        )
        attempt_id = AttemptId(row["attempt_id"])
        spec = AttemptPersistenceSpec(
            attempt_id=attempt_id,
            fold_key=key,
            ordinal=row["ordinal"],
            parent_attempt_id=(
                None
                if row["parent_attempt_id"] is None
                else AttemptId(row["parent_attempt_id"])
            ),
            resume_from_run_id=(
                None
                if row["resume_from_run_id"] is None
                else BacktestRunId(row["resume_from_run_id"])
            ),
            reproduction_fingerprint=ContentHash(row["reproduction_fingerprint"]),
            created_at=_dt(row["created_at_epoch_us"]),
        )
        projection = AttemptProjection(
            attempt_id=attempt_id,
            status=ExperimentStatus(row["status"]),
            backtest_run_id=(
                None
                if row["backtest_run_id"] is None
                else BacktestRunId(row["backtest_run_id"])
            ),
            checkpoint_ref=(
                None
                if row["checkpoint_ref"] is None
                else CheckpointRef(row["checkpoint_ref"])
            ),
            failure_code=_failure(row["failure_code"]),
            created_at=_dt(row["created_at_epoch_us"]),
            updated_at=_dt(row["updated_at_epoch_us"]),
            revision=row["revision"],
        )
        return AttemptView(spec, projection)

    def list_status_events(
        self, experiment_id: ExperimentId
    ) -> tuple[StatusEventRecord, ...]:
        rows = (
            self._database.get_connection()
            .execute(
                """
            SELECT * FROM experiment_status_event WHERE experiment_id=?
            ORDER BY
                occurred_at_epoch_us,
                CASE subject_type
                    WHEN 'experiment' THEN 0
                    WHEN 'fold' THEN 1
                    WHEN 'attempt' THEN 2
                END,
                experiment_id,
                candidate_id,
                fold_id,
                attempt_id,
                subject_revision
            """,
                (str(experiment_id),),
            )
            .fetchall()
        )
        events: list[StatusEventRecord] = []
        for row in rows:
            expected_event_id = canonical_status_event_id(
                subject_type=row["subject_type"],
                experiment_id=row["experiment_id"],
                candidate_id=row["candidate_id"],
                fold_id=row["fold_id"],
                attempt_id=row["attempt_id"],
                revision=row["subject_revision"],
            )
            if row["event_id"] != expected_event_id:
                raise _integrity(
                    "status event ID disagrees with its canonical lineage",
                    "status_event_id_mismatch",
                    event_id=row["event_id"],
                    expected_event_id=expected_event_id,
                )
            detail = _json_object(row["detail_json"], "detail_json")
            detail_payload = canonical_payload(detail)
            if str(detail_payload.content_hash) != row["detail_hash"]:
                raise _integrity(
                    "status event detail hash mismatch",
                    "status_event_detail_hash_mismatch",
                    event_id=row["event_id"],
                )
            events.append(
                StatusEventRecord(
                    event_id=row["event_id"],
                    experiment_id=ExperimentId(row["experiment_id"]),
                    candidate_id=(
                        None
                        if row["candidate_id"] is None
                        else CandidateId(row["candidate_id"])
                    ),
                    fold_id=None if row["fold_id"] is None else FoldId(row["fold_id"]),
                    attempt_id=(
                        None
                        if row["attempt_id"] is None
                        else AttemptId(row["attempt_id"])
                    ),
                    subject_type=StatusSubjectType(row["subject_type"]),
                    subject_revision=row["subject_revision"],
                    previous_status=(
                        None
                        if row["previous_status"] is None
                        else ExperimentStatus(row["previous_status"])
                    ),
                    status=ExperimentStatus(row["status"]),
                    desired_state=(
                        None
                        if row["desired_state"] is None
                        else ExperimentDesiredState(row["desired_state"])
                    ),
                    stage=None
                    if row["stage"] is None
                    else ExperimentStage(row["stage"]),
                    failure_code=_failure(row["failure_code"]),
                    reason_code=row["reason_code"],
                    detail=detail,
                    detail_hash=ContentHash(row["detail_hash"]),
                    occurred_at=_dt(row["occurred_at_epoch_us"]),
                )
            )
        return tuple(events)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        row = self._one(
            "SELECT * FROM research_artifact WHERE artifact_id=?", (artifact_id,)
        )
        if row is None:
            return None
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            experiment_id=ExperimentId(row["experiment_id"]),
            candidate_id=None
            if row["candidate_id"] is None
            else CandidateId(row["candidate_id"]),
            fold_id=None if row["fold_id"] is None else FoldId(row["fold_id"]),
            attempt_id=None
            if row["attempt_id"] is None
            else AttemptId(row["attempt_id"]),
            artifact_kind=row["artifact_kind"],
            relative_path=row["relative_path"],
            content_hash=ContentHash(row["content_hash"]),
            schema_hash=ContentHash(row["schema_hash"]),
            row_count=row["row_count"],
            byte_size=row["byte_size"],
            reproduction_fingerprint=ContentHash(row["reproduction_fingerprint"]),
            manifest=_json_object(row["manifest_json"], "manifest_json"),
            is_pinned=bool(row["is_pinned"]),
            pinned_at=None
            if row["pinned_at_epoch_us"] is None
            else _dt(row["pinned_at_epoch_us"]),
            created_at=_dt(row["created_at_epoch_us"]),
            revision=row["revision"],
        )

    def get_artifact_by_relative_path(
        self, relative_path: str
    ) -> ArtifactRecord | None:
        """Read one immutable artifact by its globally unique canonical path."""
        row = self._one(
            "SELECT artifact_id FROM research_artifact WHERE relative_path=?",
            (relative_path,),
        )
        return None if row is None else self.get_artifact(row["artifact_id"])

    def get_review_packet(self, bundle_hash: str) -> ReviewPacket | None:
        """Load one review packet by its canonical bundle hash, verifying bytes."""
        row = self._one(
            """
            SELECT artifact_id, relative_path
            FROM research_artifact
            WHERE artifact_kind='review_packet' AND reproduction_fingerprint=?
            """,
            (bundle_hash,),
        )
        if row is None:
            return None
        return self._load_verified_review_packet(
            str(row["artifact_id"]),
            str(row["relative_path"]),
            bundle_hash,
        )

    def get_review_packet_for_experiment(
        self, experiment_id: ExperimentId
    ) -> ReviewPacket | None:
        """
        Load one experiment's review packet by its lineage identity.

        Each experiment owns at most one review packet (fixed canonical path);
        the defensive ``ORDER BY ... LIMIT 1`` keeps this robust if that
        invariant ever relaxes. Bytes are re-read and the bundle hash is
        verified against the indexed reproduction fingerprint.
        """
        row = self._one(
            """
            SELECT artifact_id, relative_path, reproduction_fingerprint
            FROM research_artifact
            WHERE experiment_id=? AND artifact_kind='review_packet'
            ORDER BY created_at_epoch_us DESC
            LIMIT 1
            """,
            (str(experiment_id),),
        )
        if row is None:
            return None
        return self._load_verified_review_packet(
            str(row["artifact_id"]),
            str(row["relative_path"]),
            str(row["reproduction_fingerprint"]),
        )

    def _load_verified_review_packet(
        self, artifact_id: str, relative_path: str, expected_hash: str
    ) -> ReviewPacket:
        """Read one review packet payload and verify its bundle hash identity."""
        target = self._database.artifact_root / Path(relative_path)
        payload = _json_object(target.read_text(encoding="utf-8"), "review_packet")
        verified = review_packet_from_payload(payload)
        if str(verified.bundle_hash) != expected_hash:
            raise _integrity(
                "review packet bundle hash disagrees with its indexed identity",
                "review_packet_bundle_hash_mismatch",
                artifact_id=artifact_id,
            )
        return verified

    def get_gate_evaluation(self, evaluation_id: str) -> GateEvaluationRecord | None:
        row = self._one(
            "SELECT * FROM gate_evaluation WHERE evaluation_id=?", (evaluation_id,)
        )
        if row is None:
            return None
        return self._gate_evaluation(row)

    def list_gate_evaluations(
        self, experiment_id: ExperimentId
    ) -> tuple[GateEvaluationRecord, ...]:
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN")
            rows = connection.execute(
                """
                SELECT * FROM gate_evaluation
                WHERE experiment_id=? ORDER BY evaluation_id
                """,
                (str(experiment_id),),
            ).fetchall()
            records = tuple(self._gate_evaluation(row) for row in rows)
            connection.commit()
            return records
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "experiment read failed",
                details={"reason_code": "experiment_read_failed"},
            ) from exc
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _gate_evaluation(row: sqlite3.Row) -> GateEvaluationRecord:
        record = GateEvaluationRecord(
            evaluation_id=row["evaluation_id"],
            experiment_id=ExperimentId(row["experiment_id"]),
            candidate_id=None
            if row["candidate_id"] is None
            else CandidateId(row["candidate_id"]),
            fold_id=None if row["fold_id"] is None else FoldId(row["fold_id"]),
            attempt_id=None
            if row["attempt_id"] is None
            else AttemptId(row["attempt_id"]),
            rule_id=row["rule_id"],
            policy_version=row["policy_version"],
            layer=row["layer"],
            outcome=row["outcome"],
            observed=json.loads(row["observed_json"]),
            policy=json.loads(row["policy_json"]),
            artifact_id=row["artifact_id"],
            evaluated_at=_dt(row["evaluated_at_epoch_us"]),
        )
        if str(record.payload_hash) != row["payload_hash"]:
            raise _integrity(
                "gate evaluation payload hash mismatch",
                "gate_payload_hash_mismatch",
                evaluation_id=row["evaluation_id"],
            )
        return record

    def get_holdout_claim(self, claim_id: str) -> HoldoutClaimRecord | None:
        row = self._one("SELECT * FROM holdout_claim WHERE claim_id=?", (claim_id,))
        return None if row is None else holdout_claim_from_row(row)

    def get_holdout_claim_for_experiment(
        self,
        experiment_id: ExperimentId,
    ) -> HoldoutClaimRecord | None:
        row = self._one(
            "SELECT * FROM holdout_claim WHERE experiment_id=?",
            (str(experiment_id),),
        )
        return None if row is None else holdout_claim_from_row(row)

    def get_scheduler_slot(self) -> SchedulerSlot:
        row = self._one(
            "SELECT * FROM experiment_scheduler_slot WHERE slot_id='global'", ()
        )
        if row is None:
            raise _integrity(
                "global scheduler slot is absent", "scheduler_slot_missing"
            )
        return SchedulerSlot(
            slot_id=row["slot_id"],
            experiment_id=(
                None
                if row["experiment_id"] is None
                else ExperimentId(row["experiment_id"])
            ),
            owner_token=row["owner_token"],
            lease_until_epoch_us=row["lease_until_epoch_us"],
            acquired_at_epoch_us=row["acquired_at_epoch_us"],
            renewed_at_epoch_us=row["renewed_at_epoch_us"],
            revision=row["revision"],
        )
