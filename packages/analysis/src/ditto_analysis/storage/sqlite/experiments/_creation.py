"""Atomic experiment aggregate creation and shared status-event insertion."""

# Approved typed command surfaces intentionally carry explicit event fields.
# ruff: noqa: PLR0913

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import (
    CanonicalPayload,
    ResearchCycleIdentity,
    canonical_payload,
    encode_candidate_parameters,
    encode_launch_spec,
)
from ditto_analysis.experiments.specs import CandidateSpec, ExperimentLaunchSpec
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)


def _epoch_us(value: datetime) -> int:
    require_utc_datetime(value, "datetime")
    return int(value.timestamp() * 1_000_000)


def _persistence_error(
    message: str, reason_code: str, **details: object
) -> ExperimentPersistenceError:
    return ExperimentPersistenceError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _integrity(
    message: str, reason_code: str, **details: object
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _conflict(
    message: str, reason_code: str, **details: object
) -> ExperimentConflictError:
    return ExperimentConflictError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _optional(value: object | None) -> str | None:
    return None if value is None else str(value)


class SQLiteExperimentCreationMixin:
    """Create immutable launch aggregates and append canonical status events."""

    _database: ResearchExperimentDatabase

    def create_experiment(
        self,
        cycle: ResearchCycleIdentity,
        spec: ExperimentLaunchSpec,
        initial_record: ExperimentRecord,
    ) -> None:
        """Atomically insert an experiment, all candidates, and its revision-0 event."""
        self._validate_initial_experiment(spec, initial_record)
        launch = encode_launch_spec(spec)
        candidates = tuple(
            (candidate, encode_candidate_parameters(candidate.parameters))
            for candidate in spec.candidates
        )
        expected_experiment = (
            str(spec.experiment_id),
            cycle.cycle_id,
            str(cycle.cycle_hash),
            str(spec.strategy_version),
            str(spec.strategy_spec_hash),
            str(spec.snapshot_id),
            launch.schema_version,
            launch.json_bytes.decode("utf-8"),
            str(launch.content_hash),
            None,
            initial_record.status.value,
            initial_record.desired_state.value,
            initial_record.stage.value,
            _optional(initial_record.failure_code),
            _epoch_us(initial_record.created_at),
            _epoch_us(initial_record.created_at),
            0,
        )
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM experiment WHERE experiment_id=?",
                (str(spec.experiment_id),),
            ).fetchone()
            if existing is not None:
                self._verify_experiment_replay(
                    connection,
                    expected_experiment,
                    candidates,
                )
                connection.commit()
                return
            connection.execute(
                """
                INSERT INTO experiment(
                    experiment_id, research_cycle_id, research_cycle_hash,
                    strategy_version, strategy_spec_hash, snapshot_id,
                    launch_spec_schema_version, launch_spec_json, launch_spec_hash,
                    queue_ordinal, status, desired_state, stage, failure_code,
                    created_at_epoch_us, updated_at_epoch_us, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                expected_experiment,
            )
            for candidate, payload in candidates:
                connection.execute(
                    """
                    INSERT INTO experiment_candidate(
                        experiment_id, candidate_id, ordinal, is_baseline,
                        parameters_json, parameters_hash
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(spec.experiment_id),
                        str(candidate.candidate_id),
                        candidate.ordinal,
                        int(candidate.is_baseline),
                        payload.json_bytes.decode("utf-8"),
                        str(payload.content_hash),
                    ),
                )
            self._insert_event(
                connection,
                subject_type="experiment",
                experiment_id=str(spec.experiment_id),
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                revision=0,
                previous_status=None,
                status=initial_record.status,
                desired_state=initial_record.desired_state,
                stage=initial_record.stage,
                failure_code=initial_record.failure_code,
                reason_code="experiment_created",
                detail={},
                occurred_at=initial_record.created_at,
            )
            connection.commit()
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence_error(
                "experiment aggregate insert failed and was rolled back",
                "experiment_aggregate_insert_failed",
                sqlite_error=type(exc).__name__,
            ) from exc

    @staticmethod
    def _validate_initial_experiment(
        spec: ExperimentLaunchSpec,
        record: ExperimentRecord,
    ) -> None:
        if (
            record.experiment_id != spec.experiment_id
            or record.status is not ExperimentStatus.DRAFT
            or record.stage is not ExperimentStage.PREFLIGHT
            or record.desired_state is not spec.desired_state
            or record.created_at != spec.created_at
            or record.failure_code is not None
        ):
            raise ExperimentSpecError(
                "initial experiment projection must align with the launch spec",
                details={"reason_code": "invalid_initial_experiment_projection"},
            )

    @staticmethod
    def _verify_experiment_replay(
        connection: sqlite3.Connection,
        expected_experiment: tuple[object, ...],
        candidates: tuple[tuple[CandidateSpec, CanonicalPayload], ...],
    ) -> None:
        existing = connection.execute(
            "SELECT * FROM experiment WHERE experiment_id=?",
            (expected_experiment[0],),
        ).fetchone()
        if existing is None:
            raise _integrity(
                "experiment disappeared while its write lock was held",
                "experiment_replay_missing",
            )
        if tuple(existing) != expected_experiment:
            raise _conflict(
                "experiment identity was replayed with different immutable data",
                "experiment_replay_drift",
                experiment_id=expected_experiment[0],
            )
        expected_candidates = tuple(
            (
                expected_experiment[0],
                str(candidate.candidate_id),
                candidate.ordinal,
                int(candidate.is_baseline),
                payload.json_bytes.decode("utf-8"),
                str(payload.content_hash),
            )
            for candidate, payload in candidates
        )
        actual_candidates = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT * FROM experiment_candidate
                WHERE experiment_id=? ORDER BY ordinal
                """,
                (expected_experiment[0],),
            )
        )
        event_count = connection.execute(
            """
            SELECT count(*) FROM experiment_status_event
            WHERE experiment_id=? AND subject_type='experiment' AND subject_revision=0
            """,
            (expected_experiment[0],),
        ).fetchone()[0]
        if actual_candidates != expected_candidates or event_count != 1:
            raise _conflict(
                "experiment aggregate replay found partial or drifted children",
                "experiment_aggregate_replay_drift",
                experiment_id=expected_experiment[0],
            )

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
    ) -> None:
        payload = canonical_payload(detail)
        lineage = ":".join(
            item
            for item in (experiment_id, candidate_id, fold_id, attempt_id)
            if item is not None
        )
        subject_order = {"experiment": 0, "fold": 1, "attempt": 2}[subject_type]
        event_id = f"status:{subject_order}:{subject_type}:{lineage}:{revision}"
        connection.execute(
            """
            INSERT INTO experiment_status_event(
                event_id, experiment_id, candidate_id, fold_id, attempt_id,
                subject_type, subject_revision, previous_status, status,
                desired_state, stage, failure_code, reason_code, detail_json,
                detail_hash, occurred_at_epoch_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                _epoch_us(occurred_at),
            ),
        )
