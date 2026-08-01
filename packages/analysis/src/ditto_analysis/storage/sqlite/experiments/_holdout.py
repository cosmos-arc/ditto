"""Atomic one-shot holdout selection authority for research experiments."""

# The approved command and persistence boundary deliberately stay explicit.
# ruff: noqa: PLR0913

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from typing import TYPE_CHECKING, cast

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments._time import (
    datetime_from_epoch_us as _dt,
)
from ditto_analysis.experiments._time import (
    epoch_us as _epoch_us,
)
from ditto_analysis.experiments.holdout import (
    AtomicHoldoutClaimReceipt,
    HoldoutClaimAuthorityCommand,
    holdout_request_payload,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    SnapshotId,
)
from ditto_analysis.experiments.persistence import (
    DateWindow,
    FoldKey,
    HoldoutClaimRecord,
    LeaseFence,
    ResearchCycleIdentity,
    canonical_payload,
)
from ditto_analysis.experiments.specs import (
    CandidateExecutionBinding,
    CandidateSpec,
    ExperimentLaunchSpec,
)
from ditto_analysis.storage.sqlite.experiments._events import (
    canonical_status_event_id,
    event_values,
)
from ditto_analysis.storage.sqlite.experiments._holdout_consumption import (
    find_holdout_consumption_conflict,
)
from ditto_analysis.storage.sqlite.experiments._holdout_isolation import (
    validate_candidate_isolated_holdout,
)
from ditto_analysis.storage.sqlite.experiments._holdout_preflight import (
    validate_holdout_preflight,
)
from ditto_analysis.storage.sqlite.experiments._holdout_replay import (
    validate_holdout_replay_history,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)

if TYPE_CHECKING:
    from ditto_analysis.storage.sqlite.experiments.reader import (
        SQLiteExperimentReader,
    )


def _conflict(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentConflictError:
    return ExperimentConflictError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


def _spec(message: str, reason_code: str) -> ExperimentSpecError:
    return ExperimentSpecError(message, details={"reason_code": reason_code})


def holdout_claim_from_row(row: sqlite3.Row) -> HoldoutClaimRecord:
    """Decode and hash-check one immutable holdout claim row."""
    try:
        selection_reason = json.loads(row["selection_reason_json"])
    except json.JSONDecodeError as exc:
        raise _integrity(
            "holdout selection reason is invalid JSON",
            "holdout_claim_payload_invalid",
        ) from exc
    if not isinstance(selection_reason, dict):
        raise _integrity(
            "holdout selection reason is not an object",
            "holdout_claim_payload_invalid",
        )
    record = HoldoutClaimRecord(
        claim_id=row["claim_id"],
        cycle=ResearchCycleIdentity(
            row["research_cycle_id"], ContentHash(row["research_cycle_hash"])
        ),
        fold_key=FoldKey(
            ExperimentId(row["experiment_id"]),
            CandidateId(row["candidate_id"]),
            FoldId(row["fold_id"]),
        ),
        resolved_spec_hash=ContentHash(row["resolved_spec_hash"]),
        parameters_hash=ContentHash(row["parameters_hash"]),
        snapshot_id=SnapshotId(row["snapshot_id"]),
        window=DateWindow(
            date.fromisoformat(row["window_start"]),
            date.fromisoformat(row["window_end"]),
        ),
        reproduction_fingerprint=ContentHash(row["reproduction_fingerprint"]),
        logical_run_id=row["logical_run_id"],
        operator_confirmation=row["operator_confirmation"],
        selection_reason=cast("Mapping[str, object]", selection_reason),
        claimed_at=_dt(row["claimed_at_epoch_us"]),
    )
    if str(record.claim_payload_hash) != row["claim_payload_hash"]:
        raise _integrity(
            "holdout claim payload hash mismatch",
            "holdout_claim_hash_mismatch",
        )
    if record.claim_id != _claim_id(
        record.cycle
    ) or record.logical_run_id != _logical_run_id(
        record.claim_id,
        record.fold_key,
        record.reproduction_fingerprint,
    ):
        raise _integrity(
            "holdout claim derived identity is not canonical",
            "holdout_claim_derived_identity_drift",
        )
    return record


def _claim_id(cycle: ResearchCycleIdentity) -> str:
    identity = canonical_payload(
        {
            "schema_version": 1,
            "research_cycle_id": cycle.cycle_id,
            "research_cycle_hash": str(cycle.cycle_hash),
        }
    )
    return f"holdout:{identity.content_hash}"


def _logical_run_id(
    claim_id: str,
    fold_key: FoldKey,
    fingerprint: ContentHash,
) -> str:
    identity = canonical_payload(
        {
            "schema_version": 1,
            "claim_id": claim_id,
            "experiment_id": str(fold_key.experiment_id),
            "candidate_id": str(fold_key.candidate_id),
            "fold_id": str(fold_key.fold_id),
            "reproduction_fingerprint": str(fingerprint),
        }
    )
    return f"holdout-run:{identity.content_hash}"


def _event_detail(
    record: HoldoutClaimRecord,
    extension: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    detail: dict[str, object] = {
        "schema_version": 1,
        "claim_id": record.claim_id,
        "claim_payload_hash": str(record.claim_payload_hash),
        "candidate_id": str(record.fold_key.candidate_id),
        "fold_id": str(record.fold_key.fold_id),
        "logical_run_id": record.logical_run_id,
        "reproduction_fingerprint": str(record.reproduction_fingerprint),
        "operator_confirmation": record.operator_confirmation,
        "selection_request": record.selection_reason,
    }
    if extension is not None:
        overlap = set(detail).intersection(extension)
        if overlap:
            raise _spec(
                "holdout event detail extension overlaps canonical fields",
                "holdout_event_detail_extension_conflict",
            )
        detail.update(extension)
    canonical_payload(detail)
    return detail


def _resolved_holdout_rows(
    connection: sqlite3.Connection,
    holdout: tuple[sqlite3.Row, ...],
    candidate_id: CandidateId,
) -> tuple[sqlite3.Row, tuple[sqlite3.Row, ...]]:
    selected = tuple(row for row in holdout if row["candidate_id"] == str(candidate_id))
    if len(selected) != 1:
        raise _integrity(
            "selected candidate must have one holdout fold",
            "holdout_fold_ambiguous",
        )
    selected_row = selected[0]
    if (
        selected_row["status"] != ExperimentStatus.QUEUED.value
        or selected_row["claim_owner_token"] is not None
    ):
        raise _spec(
            "selected holdout fold must be pristine and queued",
            "holdout_fold_not_pristine",
        )
    unselected = tuple(row for row in holdout if row is not selected_row)
    for row in unselected:
        if (
            row["status"] == ExperimentStatus.QUEUED.value
            and row["claim_owner_token"] is None
        ):
            continue
        if row["status"] == ExperimentStatus.CANCELLED.value:
            validate_candidate_isolated_holdout(connection, row)
            continue
        raise _spec(
            "unselected holdout fold is neither pristine nor isolated",
            "holdout_fold_not_pristine",
        )
    return selected_row, unselected


class SQLiteHoldoutClaimMixin:
    """Claim the sealed holdout and advance its aggregate in one transaction."""

    _database: ResearchExperimentDatabase
    _reader: SQLiteExperimentReader

    @classmethod
    def _validate_lease(
        cls,
        connection: sqlite3.Connection,
        fence: LeaseFence,
        now_epoch_us: int,
        expected_experiment_id: ExperimentId,
    ) -> sqlite3.Row: ...

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
    ) -> None: ...

    def claim_holdout_candidate(
        self,
        command: HoldoutClaimAuthorityCommand,
        *,
        lease_fence: LeaseFence | None,
        now_epoch_us: int | None,
    ) -> AtomicHoldoutClaimReceipt:
        """Persist one exact candidate selection or return its exact replay."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            experiment = connection.execute(
                "SELECT * FROM experiment WHERE experiment_id=?",
                (str(command.experiment_id),),
            ).fetchone()
            rows = self._matching_claims(connection, command, experiment)
            if rows:
                receipt = self._exact_replay(connection, command, rows)
                connection.commit()
                return receipt
            if experiment is None:
                raise _integrity("experiment does not exist", "experiment_not_found")
            authority = validate_holdout_preflight(connection, command.experiment_id)
            conflict = find_holdout_consumption_conflict(
                connection,
                authority,
                holdout_claim_from_row,
            )
            if conflict is not None:
                raise _conflict(
                    "holdout consumption authority was already used",
                    "holdout_consumption_already_claimed",
                    code="HOLDOUT_ALREADY_CLAIMED",
                    claim_id=conflict.claim_id,
                    experiment_id=str(conflict.fold_key.experiment_id),
                    candidate_id=str(conflict.fold_key.candidate_id),
                    fold_id=str(conflict.fold_key.fold_id),
                    logical_run_id=conflict.logical_run_id,
                )
            self._validate_new_authority(
                connection,
                command,
                experiment,
                lease_fence,
                now_epoch_us,
            )
            launch = self._reader.get_launch_spec(command.experiment_id)
            if launch is None:
                raise _integrity("launch spec is absent", "launch_spec_missing")
            candidate, binding, selected_fold, unselected = self._resolve_selection(
                connection,
                command,
                launch,
            )
            fingerprint = command.resolved_reproduction_fingerprint
            if fingerprint is None:
                raise _spec(
                    "new holdout claim requires a resolved fingerprint",
                    "holdout_fingerprint_required",
                )
            cycle = ResearchCycleIdentity(
                experiment["research_cycle_id"],
                ContentHash(experiment["research_cycle_hash"]),
            )
            claim_id = _claim_id(cycle)
            fold_key = FoldKey(
                command.experiment_id,
                command.candidate_id,
                FoldId(selected_fold["fold_id"]),
            )
            record = HoldoutClaimRecord(
                claim_id=claim_id,
                cycle=cycle,
                fold_key=fold_key,
                resolved_spec_hash=binding.resolved_spec_hash,
                parameters_hash=candidate.parameter_hash,
                snapshot_id=launch.snapshot_id,
                window=DateWindow(
                    date.fromisoformat(selected_fold["test_start"]),
                    date.fromisoformat(selected_fold["test_end"]),
                ),
                reproduction_fingerprint=fingerprint,
                logical_run_id=_logical_run_id(claim_id, fold_key, fingerprint),
                operator_confirmation=command.operator_confirmation,
                selection_reason=holdout_request_payload(command),
                claimed_at=command.occurred_at,
            )
            self._insert_claim(connection, record)
            revision = command.expected_revision + 1
            cursor = connection.execute(
                """
                UPDATE experiment
                SET stage='holdout', updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND revision=? AND status='running'
                  AND desired_state='run' AND stage='candidate_selection'
                """,
                (
                    _epoch_us(command.occurred_at),
                    revision,
                    str(command.experiment_id),
                    command.expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("holdout stage CAS lost", "stale_projection_revision")
            self._insert_event(
                connection,
                subject_type="experiment",
                experiment_id=str(command.experiment_id),
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                revision=revision,
                previous_status=ExperimentStatus.RUNNING,
                status=ExperimentStatus.RUNNING,
                desired_state=ExperimentDesiredState.RUN,
                stage=ExperimentStage.HOLDOUT,
                failure_code=None,
                reason_code="holdout_candidate_claimed",
                detail=_event_detail(record, command.event_detail_extension),
                occurred_at=command.occurred_at,
            )
            self._cancel_unselected(connection, record, unselected)
            connection.commit()
            return AtomicHoldoutClaimReceipt(
                claim=record,
                experiment_revision=revision,
                event_id=canonical_status_event_id(
                    subject_type="experiment",
                    experiment_id=str(command.experiment_id),
                    candidate_id=None,
                    fold_id=None,
                    attempt_id=None,
                    revision=revision,
                ),
            )
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise ExperimentPersistenceError(
                "holdout claim failed and was rolled back",
                details={
                    "reason_code": "holdout_claim_failed",
                    "sqlite_error": type(exc).__name__,
                },
            ) from exc
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _matching_claims(
        connection: sqlite3.Connection,
        command: HoldoutClaimAuthorityCommand,
        experiment: sqlite3.Row | None,
    ) -> tuple[sqlite3.Row, ...]:
        cycle_id: str | None = None
        cycle_hash: str | None = None
        claim_id: str | None = None
        if experiment is not None:
            cycle_id = cast("str", experiment["research_cycle_id"])
            cycle_hash = cast("str", experiment["research_cycle_hash"])
            claim_id = _claim_id(
                ResearchCycleIdentity(cycle_id, ContentHash(cycle_hash))
            )
        fold_rows = connection.execute(
            """
            SELECT fold_id FROM experiment_fold
            WHERE experiment_id=? AND candidate_id=? AND fold_role='holdout'
            ORDER BY ordinal, fold_id
            """,
            (str(command.experiment_id), str(command.candidate_id)),
        ).fetchall()
        fold_id = fold_rows[0]["fold_id"] if len(fold_rows) == 1 else None
        logical_run_id = (
            _logical_run_id(
                claim_id,
                FoldKey(
                    command.experiment_id,
                    command.candidate_id,
                    FoldId(fold_id),
                ),
                command.resolved_reproduction_fingerprint,
            )
            if claim_id is not None
            and fold_id is not None
            and command.resolved_reproduction_fingerprint is not None
            else None
        )
        rows = connection.execute(
            """
            SELECT * FROM holdout_claim
            WHERE claim_id IS ? OR research_cycle_id IS ?
               OR research_cycle_hash IS ? OR experiment_id=?
               OR logical_run_id IS ?
               OR (
                   experiment_id=? AND candidate_id=? AND fold_id IS ?
               )
            ORDER BY claim_id
            """,
            (
                claim_id,
                cycle_id,
                cycle_hash,
                str(command.experiment_id),
                logical_run_id,
                str(command.experiment_id),
                str(command.candidate_id),
                fold_id,
            ),
        ).fetchall()
        if len({row["claim_id"] for row in rows}) > 1:
            raise _integrity(
                "holdout uniqueness keys resolve to different claims",
                "holdout_claim_uniqueness_drift",
            )
        return tuple(rows)

    @staticmethod
    def _exact_replay(
        connection: sqlite3.Connection,
        command: HoldoutClaimAuthorityCommand,
        rows: tuple[sqlite3.Row, ...],
    ) -> AtomicHoldoutClaimReceipt:
        record = holdout_claim_from_row(rows[0])
        expected_request = holdout_request_payload(command)
        fingerprint_matches = (
            command.resolved_reproduction_fingerprint is None
            or command.resolved_reproduction_fingerprint
            == record.reproduction_fingerprint
        )
        if (
            record.fold_key.experiment_id != command.experiment_id
            or record.fold_key.candidate_id != command.candidate_id
            or record.operator_confirmation != command.operator_confirmation
            or record.selection_reason != expected_request
            or record.claimed_at != command.occurred_at
            or not fingerprint_matches
        ):
            raise _conflict(
                "holdout claim replay drift",
                "holdout_claim_replay_drift",
                code="HOLDOUT_ALREADY_CLAIMED",
                claim_id=record.claim_id,
                experiment_id=str(record.fold_key.experiment_id),
                candidate_id=str(record.fold_key.candidate_id),
                fold_id=str(record.fold_key.fold_id),
                logical_run_id=record.logical_run_id,
            )
        revision = command.expected_revision + 1
        expected = event_values(
            subject_type="experiment",
            experiment_id=str(command.experiment_id),
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            revision=revision,
            previous_status=ExperimentStatus.RUNNING,
            status=ExperimentStatus.RUNNING,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.HOLDOUT,
            failure_code=None,
            reason_code="holdout_candidate_claimed",
            detail=_event_detail(record, command.event_detail_extension),
            occurred_at_epoch_us=_epoch_us(command.occurred_at),
        )
        event = connection.execute(
            "SELECT * FROM experiment_status_event WHERE event_id=?", (expected[0],)
        ).fetchone()
        if event is None or tuple(event) != expected:
            raise _integrity(
                "holdout claim event is missing or drifted",
                "holdout_claim_event_drift",
            )
        validate_holdout_replay_history(connection, record)
        return AtomicHoldoutClaimReceipt(record, revision, cast("str", expected[0]))

    def _validate_new_authority(
        self,
        connection: sqlite3.Connection,
        command: HoldoutClaimAuthorityCommand,
        experiment: sqlite3.Row,
        lease_fence: LeaseFence | None,
        now_epoch_us: int | None,
    ) -> None:
        if experiment["revision"] != command.expected_revision:
            raise _conflict("experiment revision is stale", "stale_projection_revision")
        if lease_fence is None or now_epoch_us is None:
            raise _spec("new holdout claim requires a lease", "holdout_lease_required")
        self._validate_lease(
            connection, lease_fence, now_epoch_us, command.experiment_id
        )
        if (
            experiment["status"] != ExperimentStatus.RUNNING.value
            or experiment["desired_state"] != ExperimentDesiredState.RUN.value
            or experiment["stage"] != ExperimentStage.CANDIDATE_SELECTION.value
        ):
            raise _spec(
                "experiment is not ready for holdout selection",
                "holdout_claim_stage_invalid",
            )
        live_fold = connection.execute(
            """
            SELECT fold_id FROM experiment_fold
            WHERE experiment_id=? AND status='running' LIMIT 1
            """,
            (str(command.experiment_id),),
        ).fetchone()
        live_attempt = connection.execute(
            """
            SELECT attempt_id FROM experiment_attempt
            WHERE experiment_id=? AND status IN ('queued', 'running') LIMIT 1
            """,
            (str(command.experiment_id),),
        ).fetchone()
        if live_fold is not None or live_attempt is not None:
            raise _spec(
                "holdout claim cannot race live work", "holdout_live_work_exists"
            )

    @staticmethod
    def _resolve_selection(
        connection: sqlite3.Connection,
        command: HoldoutClaimAuthorityCommand,
        launch: ExperimentLaunchSpec,
    ) -> tuple[
        CandidateSpec,
        CandidateExecutionBinding,
        sqlite3.Row,
        tuple[sqlite3.Row, ...],
    ]:
        candidates = tuple(
            candidate
            for candidate in launch.candidates
            if candidate.candidate_id == command.candidate_id
        )
        bindings = tuple(
            binding
            for binding in launch.execution_bindings
            if binding.candidate_id == command.candidate_id
        )
        if len(candidates) != 1 or len(bindings) != 1:
            raise _spec("selected candidate is not frozen", "holdout_candidate_invalid")
        relational = connection.execute(
            """
            SELECT * FROM experiment_candidate
            WHERE experiment_id=? AND candidate_id=?
            """,
            (str(command.experiment_id), str(command.candidate_id)),
        ).fetchone()
        candidate = candidates[0]
        binding = bindings[0]
        if (
            relational is None
            or relational["parameters_hash"] != str(candidate.parameter_hash)
            or binding.parameter_hash != candidate.parameter_hash
        ):
            raise _integrity(
                "selected candidate binding drifted",
                "holdout_candidate_binding_drift",
            )
        folds = connection.execute(
            """
            SELECT * FROM experiment_fold WHERE experiment_id=?
            ORDER BY candidate_id, ordinal, fold_id
            """,
            (str(command.experiment_id),),
        ).fetchall()
        non_holdout = tuple(row for row in folds if row["fold_role"] != "holdout")
        selected_prior = tuple(
            row
            for row in non_holdout
            if row["candidate_id"] == str(command.candidate_id)
        )
        if not selected_prior or any(
            row["status"] != ExperimentStatus.COMPLETED.value for row in selected_prior
        ):
            raise _spec(
                "selected candidate has incomplete pre-holdout folds",
                "holdout_candidate_not_completed",
            )
        if any(row["status"] in {"queued", "running"} for row in non_holdout):
            raise _spec(
                "pre-holdout fold frontier is incomplete",
                "holdout_preselection_incomplete",
            )
        holdout = tuple(row for row in folds if row["fold_role"] == "holdout")
        expected_holdout = Counter(
            str(candidate.candidate_id) for candidate in launch.candidates
        )
        observed_holdout = Counter(row["candidate_id"] for row in holdout)
        if observed_holdout != expected_holdout:
            raise _integrity(
                "holdout fold cardinality differs from frozen candidates",
                "holdout_fold_cardinality_drift",
            )
        selected_row, unselected = _resolved_holdout_rows(
            connection,
            holdout,
            command.candidate_id,
        )
        attempt_count = connection.execute(
            """
            SELECT count(*) FROM experiment_attempt AS attempt
            JOIN experiment_fold AS fold
              ON fold.experiment_id=attempt.experiment_id
             AND fold.candidate_id=attempt.candidate_id
             AND fold.fold_id=attempt.fold_id
            WHERE fold.experiment_id=? AND fold.fold_role='holdout'
            """,
            (str(command.experiment_id),),
        ).fetchone()[0]
        if attempt_count != 0:
            raise _integrity(
                "holdout attempts exist before the first claim",
                "holdout_attempt_before_claim",
            )
        return candidate, binding, selected_row, unselected

    @staticmethod
    def _insert_claim(
        connection: sqlite3.Connection,
        record: HoldoutClaimRecord,
    ) -> None:
        reason = canonical_payload(record.selection_reason)
        connection.execute(
            """
            INSERT INTO holdout_claim(
                claim_id, research_cycle_id, research_cycle_hash, experiment_id,
                candidate_id, fold_id, fold_role, resolved_spec_hash,
                parameters_hash, snapshot_id, window_start, window_end,
                reproduction_fingerprint, logical_run_id, operator_confirmation,
                selection_reason_json, claim_payload_hash, claimed_at_epoch_us
            ) VALUES (?, ?, ?, ?, ?, ?, 'holdout', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.claim_id,
                record.cycle.cycle_id,
                str(record.cycle.cycle_hash),
                str(record.fold_key.experiment_id),
                str(record.fold_key.candidate_id),
                str(record.fold_key.fold_id),
                str(record.resolved_spec_hash),
                str(record.parameters_hash),
                str(record.snapshot_id),
                record.window.start.isoformat(),
                record.window.end.isoformat(),
                str(record.reproduction_fingerprint),
                record.logical_run_id,
                record.operator_confirmation,
                reason.json_bytes.decode("utf-8"),
                str(record.claim_payload_hash),
                _epoch_us(record.claimed_at),
            ),
        )

    def _cancel_unselected(
        self,
        connection: sqlite3.Connection,
        record: HoldoutClaimRecord,
        folds: tuple[sqlite3.Row, ...],
    ) -> None:
        for fold in folds:
            if fold["status"] == ExperimentStatus.CANCELLED.value:
                validate_candidate_isolated_holdout(connection, fold)
                continue
            revision = fold["revision"] + 1
            cursor = connection.execute(
                """
                UPDATE experiment_fold
                SET status='cancelled', claim_owner_token=NULL,
                    updated_at_epoch_us=?, revision=?
                WHERE experiment_id=? AND candidate_id=? AND fold_id=?
                  AND revision=? AND status='queued'
                """,
                (
                    _epoch_us(record.claimed_at),
                    revision,
                    fold["experiment_id"],
                    fold["candidate_id"],
                    fold["fold_id"],
                    fold["revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict(
                    "unselected holdout cancellation CAS lost",
                    "holdout_unselected_fold_conflict",
                )
            self._insert_event(
                connection,
                subject_type="fold",
                experiment_id=fold["experiment_id"],
                candidate_id=fold["candidate_id"],
                fold_id=fold["fold_id"],
                attempt_id=None,
                revision=revision,
                previous_status=ExperimentStatus.QUEUED,
                status=ExperimentStatus.CANCELLED,
                desired_state=None,
                stage=None,
                failure_code=None,
                reason_code="holdout_candidate_not_selected",
                detail={
                    "claim_id": record.claim_id,
                    "selected_candidate_id": str(record.fold_key.candidate_id),
                },
                occurred_at=record.claimed_at,
            )
