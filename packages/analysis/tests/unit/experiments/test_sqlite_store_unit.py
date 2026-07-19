"""Behavior tests for the R3 experiment SQLite control-plane store.

This path is a plan-owned placement exception: the tests exercise a real SQLite
database, but the approved Task 7 command fixes them under ``unit/experiments``.
Every database root is supplied by ``tmp_path``.
"""

# Imports inside _api are intentionally reflected into a SimpleNamespace.
# ruff: noqa: F401

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import (
    AttemptId,
    CandidateId,
    CandidateSpec,
    ContentHash,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldProtocolSpec,
    SnapshotId,
    StrategyVersion,
)

NOW = datetime(2026, 7, 19, 4, 0, tzinfo=UTC)
NOW_US = 1_768_000_000_000_000


def _api() -> SimpleNamespace:
    """Import the not-yet-existing Task 7 runtime inside each test for true RED."""
    from ditto_analysis.errors import (
        ExperimentConflictError,
        ExperimentIntegrityError,
        ExperimentPersistenceError,
    )
    from ditto_analysis.experiments.persistence import (
        ArtifactRecord,
        AttemptPersistenceSpec,
        AttemptProjection,
        DateWindow,
        FoldKey,
        FoldPersistenceSpec,
        FoldProjection,
        FoldRole,
        GateEvaluationRecord,
        HoldoutClaimRecord,
        ResearchCycleIdentity,
        canonical_payload,
        decode_launch_spec,
        encode_launch_spec,
    )
    from ditto_analysis.storage.sqlite.experiments import (
        ResearchExperimentDatabase,
        SQLiteExperimentReader,
        SQLiteExperimentWriter,
    )

    return SimpleNamespace(**locals())


def _candidate(
    ordinal: int,
    *,
    baseline: bool = False,
    parameters: dict[str, object] | None = None,
) -> CandidateSpec:
    return CandidateSpec(
        candidate_id=CandidateId(f"candidate-{ordinal}"),
        ordinal=ordinal,
        is_baseline=baseline,
        parameters=parameters or {"lookback": ordinal * 20, "alpha": 0.05},
    )


def _launch(
    *,
    experiment_id: str = "experiment-1",
    candidates: tuple[CandidateSpec, ...] | None = None,
) -> ExperimentLaunchSpec:
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId(experiment_id),
        strategy_version=StrategyVersion("stock-selection@3"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-certified-1"),
        candidates=candidates or (_candidate(1, baseline=True), _candidate(2)),
        fold_protocol=FoldProtocolSpec(
            protocol_id="r3-walk-forward",
            protocol_version=1,
            protocol_hash=ContentHash("b" * 64),
        ),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(candidate_limit=128, fold_run_limit=1024),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _record(experiment_id: str = "experiment-1") -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=ExperimentId(experiment_id),
        status=ExperimentStatus.DRAFT,
        desired_state=ExperimentDesiredState.RUN,
        stage=ExperimentStage.PREFLIGHT,
        created_at=NOW,
    )


def _store(tmp_path: Path) -> tuple[Any, Any, Any, SimpleNamespace]:
    api = _api()
    database = api.ResearchExperimentDatabase(tmp_path)
    database.initialize()
    return (
        database,
        api.SQLiteExperimentReader(database),
        api.SQLiteExperimentWriter(database),
        api,
    )


def _create_experiment(writer: Any, api: SimpleNamespace) -> None:
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64)),
        _launch(),
        _record(),
    )


def _fold_spec(api: SimpleNamespace, *, role: str = "walk_forward") -> Any:
    key = api.FoldKey(
        ExperimentId("experiment-1"),
        CandidateId("candidate-1"),
        FoldId("fold-1"),
    )
    return api.FoldPersistenceSpec.create(
        key=key,
        ordinal=1,
        fold_role=api.FoldRole(role),
        train_window=(
            None
            if role == "exploration"
            else api.DateWindow(date(2024, 1, 2), date(2025, 12, 31))
        ),
        test_window=api.DateWindow(date(2026, 1, 5), date(2026, 3, 31)),
        purge_sessions=2,
        embargo_sessions=1,
    )


def _fold_projection(api: SimpleNamespace, spec: Any) -> Any:
    return api.FoldProjection(
        key=spec.key,
        status=ExperimentStatus.QUEUED,
        claim_owner_token=None,
        created_at=NOW,
        updated_at=NOW,
        revision=0,
    )


def _add_fold(writer: Any, api: SimpleNamespace, *, role: str = "walk_forward") -> Any:
    spec = _fold_spec(api, role=role)
    writer.add_fold(spec, _fold_projection(api, spec))
    return spec


def _attempt_spec(api: SimpleNamespace, fold_key: Any) -> Any:
    return api.AttemptPersistenceSpec(
        attempt_id=AttemptId("attempt-1"),
        fold_key=fold_key,
        ordinal=1,
        parent_attempt_id=None,
        resume_from_run_id=None,
        reproduction_fingerprint=ContentHash("d" * 64),
        created_at=NOW,
    )


def _attempt_projection(api: SimpleNamespace) -> Any:
    return api.AttemptProjection(
        attempt_id=AttemptId("attempt-1"),
        status=ExperimentStatus.QUEUED,
        backtest_run_id=None,
        checkpoint_ref=None,
        failure_code=None,
        created_at=NOW,
        updated_at=NOW,
        revision=0,
    )


def _dispatch_first_attempt(
    writer: Any,
    api: SimpleNamespace,
    fold: Any,
    *,
    owner: str = "owner-attempt",
) -> Any:
    lease = writer.try_claim_lease(
        fold.key.experiment_id,
        owner,
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    writer.claim_fold_and_add_attempt(
        fold.key,
        _attempt_spec(api, fold.key),
        _attempt_projection(api),
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
    )
    return lease


def _artifact(api: SimpleNamespace) -> Any:
    return api.ArtifactRecord(
        artifact_id="artifact-1",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId("attempt-1"),
        artifact_kind="comparison-ledger",
        relative_path="experiments/experiment-1/comparison.parquet",
        content_hash=ContentHash("1" * 64),
        schema_hash=ContentHash("2" * 64),
        row_count=2,
        byte_size=128,
        reproduction_fingerprint=ContentHash("d" * 64),
        manifest={"format": "parquet"},
        is_pinned=False,
        pinned_at=None,
        created_at=NOW,
        revision=0,
    )


def _gate(api: SimpleNamespace) -> Any:
    return api.GateEvaluationRecord(
        evaluation_id="gate-1",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId("attempt-1"),
        rule_id="minimum-oos",
        policy_version="r3-v1",
        layer="hard",
        outcome="pass",
        observed={"sessions": 60},
        policy={"minimum": 40},
        artifact_id="artifact-1",
        evaluated_at=NOW,
    )


def _holdout_claim(api: SimpleNamespace, fold_key: Any) -> Any:
    return api.HoldoutClaimRecord(
        claim_id="claim-1",
        cycle=api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64)),
        fold_key=fold_key,
        resolved_spec_hash=ContentHash("3" * 64),
        parameters_hash=api.canonical_payload(
            {"alpha": 0.05, "lookback": 20}
        ).content_hash,
        snapshot_id=SnapshotId("snapshot-certified-1"),
        window=api.DateWindow(date(2026, 1, 5), date(2026, 3, 31)),
        reproduction_fingerprint=ContentHash("d" * 64),
        logical_run_id="logical-run-1",
        operator_confirmation="approved by operator-1",
        selection_reason={"rank": 1},
        claimed_at=NOW,
    )


def _seed_all_tables(database: Any, writer: Any, api: SimpleNamespace) -> None:
    _create_experiment(writer, api)
    fold = _add_fold(writer, api, role="holdout")
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-adversarial")
    writer.add_artifact(
        _artifact(api), lease_fence=lease.fence, now_epoch_us=NOW_US + 1
    )
    writer.add_gate_evaluation(_gate(api))
    writer.claim_holdout(_holdout_claim(api, fold.key))
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM experiment_scheduler_slot")
        .fetchone()[0]
        == 1
    )


def test_launch_codec_round_trips_complete_typed_spec_and_hashes_on_read() -> None:
    api = _api()
    spec = _launch()

    encoded = api.encode_launch_spec(spec)
    decoded = api.decode_launch_spec(encoded.json_bytes, encoded.content_hash)

    assert decoded == spec
    assert encoded.schema_version == 1
    assert encoded.content_hash == ContentHash(
        hashlib.sha256(encoded.json_bytes).hexdigest()
    )


def test_canonical_payload_is_stable_across_mapping_insertion_order() -> None:
    api = _api()

    first = api.canonical_payload({"a": 1, "nested": {"x": 2, "y": [3, 4]}})
    second = api.canonical_payload({"nested": {"y": [3, 4], "x": 2}, "a": 1})

    assert first == second


def test_decode_launch_spec_rejects_hash_mismatch() -> None:
    api = _api()
    payload = api.encode_launch_spec(_launch())

    with pytest.raises(ExperimentSpecError) as exc_info:
        api.decode_launch_spec(payload.json_bytes, ContentHash("0" * 64))

    assert exc_info.value.details["reason_code"] == "canonical_payload_hash_mismatch"


def test_launch_rejects_semantically_duplicate_candidate_parameters_before_sql() -> (
    None
):
    candidates = (
        _candidate(1, baseline=True, parameters={"a": 1, "b": {"x": 2}}),
        _candidate(2, parameters={"b": {"x": 2}, "a": 1}),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(candidates=candidates)

    assert exc_info.value.details["reason_code"] == "duplicate_candidate_parameters"


def test_create_experiment_is_atomic_lossless_and_exact_replay_is_noop(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    cycle = api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64))
    spec = _launch()
    initial = _record()

    writer.create_experiment(cycle, spec, initial)
    before = database.get_connection().total_changes
    writer.create_experiment(cycle, spec, initial)

    projection = reader.get_experiment_projection(spec.experiment_id)
    assert projection is not None
    assert projection.record == initial
    assert projection.queue_ordinal is None
    assert projection.revision == 0
    assert reader.get_research_cycle_identity(spec.experiment_id) == cycle
    assert reader.get_launch_spec(spec.experiment_id) == spec
    assert [
        item.candidate_id for item in reader.list_candidates(spec.experiment_id)
    ] == [
        CandidateId("candidate-1"),
        CandidateId("candidate-2"),
    ]
    assert len(reader.list_status_events(spec.experiment_id)) == 1
    assert database.get_connection().total_changes == before


def test_create_experiment_conflicting_replay_and_partial_insert_fail_closed(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    connection = database.get_connection()
    connection.execute(
        """
        CREATE TRIGGER abort_second_candidate
        BEFORE INSERT ON experiment_candidate
        WHEN NEW.candidate_id = 'candidate-x-2'
        BEGIN
            SELECT RAISE(ABORT, 'injected candidate failure');
        END
        """
    )
    connection.commit()
    other = _launch(
        experiment_id="experiment-x",
        candidates=(
            CandidateSpec(CandidateId("candidate-x-1"), 1, True, {"x": 1}),
            CandidateSpec(CandidateId("candidate-x-2"), 2, False, {"x": 2}),
        ),
    )

    with pytest.raises(api.ExperimentPersistenceError):
        writer.create_experiment(
            api.ResearchCycleIdentity("cycle-x", ContentHash("e" * 64)),
            other,
            _record("experiment-x"),
        )
    assert reader.get_experiment_projection(other.experiment_id) is None

    drift = _launch(
        candidates=(_candidate(1, baseline=True), _candidate(2, parameters={"x": 99}))
    )
    with pytest.raises(api.ExperimentConflictError):
        writer.create_experiment(
            api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64)),
            drift,
            _record(),
        )
    assert reader.get_launch_spec(ExperimentId("experiment-1")) == _launch()


def test_add_fold_and_attempt_round_trip_full_lineage_and_revision_zero_events(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    attempt = _attempt_spec(api, fold.key)
    _dispatch_first_attempt(writer, api, fold)

    assert reader.get_fold(fold.key).spec == fold
    assert reader.list_folds(ExperimentId("experiment-1"))[0].projection.revision == 1
    assert reader.get_attempt(AttemptId("attempt-1")).spec == attempt
    assert reader.list_attempts(fold.key)[0].projection.revision == 0
    events = reader.list_status_events(ExperimentId("experiment-1"))
    assert [(event.subject_type.value, event.subject_revision) for event in events] == [
        ("experiment", 0),
        ("fold", 0),
        ("fold", 1),
        ("attempt", 0),
    ]


def test_fold_payload_must_exactly_match_every_relational_field(tmp_path: Path) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    canonical = _fold_spec(api)
    drifted = replace(canonical, embargo_sessions=canonical.embargo_sessions + 1)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.add_fold(drifted, _fold_projection(api, drifted))

    assert exc_info.value.details["reason_code"] == "fold_relation_payload_mismatch"
    assert reader.get_fold(drifted.key) is None


def test_fold_and_retry_lineage_drift_is_rejected_without_partial_rows(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold)
    retry = api.AttemptPersistenceSpec(
        attempt_id=AttemptId("attempt-2"),
        fold_key=fold.key,
        ordinal=2,
        parent_attempt_id=AttemptId("attempt-1"),
        resume_from_run_id=None,
        reproduction_fingerprint=ContentHash("e" * 64),
        created_at=NOW,
    )
    retry_projection = api.AttemptProjection(
        attempt_id=AttemptId("attempt-2"),
        status=ExperimentStatus.QUEUED,
        backtest_run_id=None,
        checkpoint_ref=None,
        failure_code=None,
        created_at=NOW,
        updated_at=NOW,
        revision=0,
    )

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.add_attempt(
            retry,
            retry_projection,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
        )

    assert exc_info.value.details["reason_code"] == "retry_fingerprint_drift"
    assert reader.get_attempt(AttemptId("attempt-2")) is None


def test_projection_cas_and_event_append_commit_or_rollback_together(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)

    queued = writer.transition_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.QUEUED,
        target_desired_state=ExperimentDesiredState.RUN,
        target_stage=ExperimentStage.PREFLIGHT,
        failure_code=None,
        queue_ordinal=1,
        expected_revision=0,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="preflight_passed",
        detail={"certified": True},
    )
    assert queued.revision == 1
    assert (
        reader.list_status_events(ExperimentId("experiment-1"))[-1].subject_revision
        == 1
    )

    connection = database.get_connection()
    connection.execute(
        """
        CREATE TRIGGER abort_revision_two_event
        BEFORE INSERT ON experiment_status_event
        WHEN NEW.subject_type = 'experiment' AND NEW.subject_revision = 2
        BEGIN
            SELECT RAISE(ABORT, 'injected event failure');
        END
        """
    )
    connection.commit()
    with pytest.raises(api.ExperimentPersistenceError):
        writer.transition_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.RUNNING,
            target_desired_state=ExperimentDesiredState.RUN,
            target_stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            queue_ordinal=1,
            expected_revision=1,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="dispatch",
            detail={},
        )
    assert reader.get_experiment_projection(ExperimentId("experiment-1")).revision == 1
    assert len(reader.list_status_events(ExperimentId("experiment-1"))) == 2


def test_operator_status_transition_cannot_change_the_current_stage(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.BLOCKED,
            target_desired_state=ExperimentDesiredState.RUN,
            target_stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            queue_ordinal=None,
            expected_revision=0,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=True,
            reason_code="preflight_blocked",
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "experiment_stage_must_be_preserved"
    assert reader.get_experiment_projection(ExperimentId("experiment-1")).revision == 0


def test_stale_cas_and_append_only_event_mutations_are_rejected(tmp_path: Path) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.transition_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.QUEUED,
            target_desired_state=ExperimentDesiredState.RUN,
            target_stage=ExperimentStage.PREFLIGHT,
            failure_code=None,
            queue_ordinal=1,
            expected_revision=7,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code=None,
            detail={},
        )
    assert exc_info.value.details["reason_code"] == "stale_projection_revision"

    event_id = reader.list_status_events(ExperimentId("experiment-1"))[0].event_id
    connection = database.get_connection()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE experiment_status_event SET detail_json='{}' WHERE event_id=?",
            (event_id,),
        )
    connection.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM experiment_status_event WHERE event_id=?", (event_id,)
        )
    connection.rollback()


@pytest.mark.parametrize("mode", ["OR REPLACE", "OR IGNORE"])
def test_conflicting_insert_modes_preserve_existing_candidate_payload(
    tmp_path: Path, mode: str
) -> None:
    database, _reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    connection = database.get_connection()
    before = tuple(
        connection.execute(
            """
            SELECT * FROM experiment_candidate
            WHERE experiment_id=? AND candidate_id=?
            """,
            ("experiment-1", "candidate-1"),
        ).fetchone()
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f"INSERT {mode} INTO experiment_candidate VALUES (?, ?, ?, ?, ?, ?)",
            ("experiment-1", "candidate-1", 99, 0, '{"drift":true}', "f" * 64),
        )
    connection.rollback()
    after = tuple(
        connection.execute(
            """
            SELECT * FROM experiment_candidate
            WHERE experiment_id=? AND candidate_id=?
            """,
            ("experiment-1", "candidate-1"),
        ).fetchone()
    )
    assert after == before


@pytest.mark.parametrize(
    "table",
    [
        "experiment",
        "experiment_candidate",
        "experiment_fold",
        "experiment_attempt",
        "experiment_status_event",
        "research_artifact",
        "gate_evaluation",
        "holdout_claim",
        "experiment_scheduler_slot",
    ],
)
@pytest.mark.parametrize("mode", ["OR REPLACE", "OR IGNORE", "UPSERT"])
@pytest.mark.parametrize("recursive_triggers", [False, True])
def test_every_table_rejects_all_conflicting_insert_modes_before_mutation(
    tmp_path: Path,
    table: str,
    mode: str,
    recursive_triggers: bool,
) -> None:
    database, _reader, writer, api = _store(tmp_path)
    _seed_all_tables(database, writer, api)
    connection = database.get_connection()
    connection.execute(
        "PRAGMA recursive_triggers=ON"
        if recursive_triggers
        else "PRAGMA recursive_triggers=OFF"
    )
    columns = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
    column_sql = ", ".join(columns)
    placeholders = ", ".join("?" for _column in columns)
    before = tuple(
        tuple(row)
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
    )
    values = before[0]
    statement = (
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT DO UPDATE SET {columns[0]}=excluded.{columns[0]}"
        if mode == "UPSERT"
        else f"INSERT {mode} INTO {table} ({column_sql}) VALUES ({placeholders})"
    )

    with pytest.raises(sqlite3.IntegrityError, match="insert conflict"):
        connection.execute(statement, values)
    connection.rollback()

    after = tuple(
        tuple(row)
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
    )
    assert after == before


@pytest.mark.parametrize(
    "table",
    ["experiment_status_event", "gate_evaluation", "holdout_claim"],
)
def test_audit_fact_tables_reject_update_and_delete(tmp_path: Path, table: str) -> None:
    database, _reader, writer, api = _store(tmp_path)
    _seed_all_tables(database, writer, api)
    connection = database.get_connection()
    before = tuple(
        tuple(row)
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
    )

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(f"UPDATE {table} SET rowid=rowid")
    connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(f"DELETE FROM {table}")
    connection.rollback()

    after = tuple(
        tuple(row)
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
    )
    assert after == before


def test_artifact_gate_and_holdout_are_typed_append_only_facts(tmp_path: Path) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api, role="holdout")
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-artifact",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    artifact = api.ArtifactRecord(
        artifact_id="artifact-1",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=None,
        artifact_kind="comparison-ledger",
        relative_path="experiments/experiment-1/comparison.parquet",
        content_hash=ContentHash("1" * 64),
        schema_hash=ContentHash("2" * 64),
        row_count=2,
        byte_size=128,
        reproduction_fingerprint=ContentHash("d" * 64),
        manifest={"format": "parquet"},
        is_pinned=False,
        pinned_at=None,
        created_at=NOW,
        revision=0,
    )
    writer.add_artifact(
        artifact,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
    )
    pinned = writer.pin_artifact("artifact-1", expected_revision=0, pinned_at=NOW)
    assert pinned.is_pinned is True
    assert pinned.revision == 1
    with pytest.raises(api.ExperimentConflictError):
        writer.pin_artifact("artifact-1", expected_revision=0, pinned_at=NOW)

    gate = api.GateEvaluationRecord(
        evaluation_id="gate-1",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=None,
        rule_id="minimum-oos",
        policy_version="r3-v1",
        layer="hard",
        outcome="pass",
        observed={"sessions": 60},
        policy={"minimum": 40},
        artifact_id="artifact-1",
        evaluated_at=NOW,
    )
    writer.add_gate_evaluation(gate)
    assert reader.get_gate_evaluation("gate-1") == gate

    claim = api.HoldoutClaimRecord(
        claim_id="claim-1",
        cycle=api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64)),
        fold_key=fold.key,
        resolved_spec_hash=ContentHash("3" * 64),
        parameters_hash=api.canonical_payload(
            {"alpha": 0.05, "lookback": 20}
        ).content_hash,
        snapshot_id=SnapshotId("snapshot-certified-1"),
        window=api.DateWindow(date(2026, 1, 5), date(2026, 3, 31)),
        reproduction_fingerprint=ContentHash("d" * 64),
        logical_run_id="logical-run-1",
        operator_confirmation="approved by operator-1",
        selection_reason={"rank": 1},
        claimed_at=NOW,
    )
    first = writer.claim_holdout(claim)
    replay = writer.claim_holdout(claim)
    assert replay == first == reader.get_holdout_claim("claim-1")


def test_holdout_claim_rejects_cycle_and_fold_role_lineage_drift(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    walk_forward = _add_fold(writer, api, role="walk_forward")

    with pytest.raises(api.ExperimentIntegrityError) as fold_exc:
        writer.claim_holdout(_holdout_claim(api, walk_forward.key))
    assert fold_exc.value.details["reason_code"] == "invalid_holdout_lineage"

    holdout = replace(
        _fold_spec(api, role="holdout"),
        key=replace(walk_forward.key, fold_id=FoldId("fold-2")),
        ordinal=2,
    )
    holdout = api.FoldPersistenceSpec.create(
        holdout.key,
        holdout.ordinal,
        holdout.fold_role,
        holdout.train_window,
        holdout.test_window,
        holdout.purge_sessions,
        holdout.embargo_sessions,
    )
    writer.add_fold(holdout, _fold_projection(api, holdout))
    wrong_cycle = replace(
        _holdout_claim(api, holdout.key),
        cycle=api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("e" * 64)),
    )
    with pytest.raises(api.ExperimentIntegrityError) as cycle_exc:
        writer.claim_holdout(wrong_cycle)
    assert cycle_exc.value.details["reason_code"] == "invalid_holdout_lineage"
    assert reader.get_holdout_claim("claim-1") is None


def test_holdout_exact_replay_is_noop_but_payload_drift_fails_closed(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api, role="holdout")
    claim = _holdout_claim(api, fold.key)
    assert writer.claim_holdout(claim) == claim
    assert writer.claim_holdout(claim) == claim

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.claim_holdout(
            replace(claim, operator_confirmation="approved by operator-2")
        )

    assert exc_info.value.details["reason_code"] == "holdout_claim_replay_drift"
    assert reader.get_holdout_claim("claim-1") == claim


@pytest.mark.parametrize(
    "relative_path",
    ["/absolute/file", "../metadata/metadata.sqlite", "a/../b", "C:/drive", "a\\b"],
)
def test_artifact_path_validation_fails_before_sql(
    tmp_path: Path, relative_path: str
) -> None:
    _database, _reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-artifact",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    artifact = api.ArtifactRecord(
        artifact_id="artifact-bad",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        artifact_kind="review-bundle",
        relative_path=relative_path,
        content_hash=ContentHash("1" * 64),
        schema_hash=ContentHash("2" * 64),
        row_count=0,
        byte_size=0,
        reproduction_fingerprint=ContentHash("d" * 64),
        manifest={},
        is_pinned=False,
        pinned_at=None,
        created_at=NOW,
        revision=0,
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.add_artifact(
            artifact,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 1,
        )

    assert exc_info.value.details["reason_code"] == "invalid_artifact_relative_path"
