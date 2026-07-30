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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import orjson
import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import (
    AttemptId,
    BacktestRunId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    CheckpointRef,
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
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SnapshotId,
    StrategyVersion,
)
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
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
    from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
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


def _objective(
    *,
    baseline_candidate_id: str = "candidate-1",
    experiment_id: str = "experiment-1",
    candidates: tuple[CandidateSpec, ...] | None = None,
) -> PromotionObjective:
    launch_candidates = candidates or (
        _candidate(1, baseline=True),
        _candidate(2),
    )
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=CandidateId(baseline_candidate_id),
        economic_rationale="Capture durable returns after costs.",
        trial_family=TrialFamilyDeclaration(
            "stock-selection-r3-v1",
            tuple(
                LogicalTrialIdentity(
                    ExperimentId(experiment_id),
                    candidate.candidate_id,
                    candidate.ordinal,
                    candidate.parameter_hash,
                    TrialKind.CURRENT,
                )
                for candidate in launch_candidates
            ),
        ),
    )


def _launch(
    *,
    experiment_id: str = "experiment-1",
    candidates: tuple[CandidateSpec, ...] | None = None,
) -> ExperimentLaunchSpec:
    launch_candidates = candidates or (
        _candidate(1, baseline=True),
        _candidate(2),
    )
    baseline = next(
        candidate for candidate in launch_candidates if candidate.is_baseline
    )
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId(experiment_id),
        strategy_version=StrategyVersion("stock-selection@3"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-certified-1"),
        candidates=launch_candidates,
        execution_bindings=tuple(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash(f"{candidate.ordinal + 16:064x}"),
            )
            for candidate in launch_candidates
        ),
        promotion_objective=_objective(
            baseline_candidate_id=str(baseline.candidate_id),
            experiment_id=experiment_id,
            candidates=launch_candidates,
        ),
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


def _fold_spec(
    api: SimpleNamespace,
    *,
    role: str = "walk_forward",
    key: Any | None = None,
    ordinal: int = 1,
) -> Any:
    key = key or api.FoldKey(
        ExperimentId("experiment-1"),
        CandidateId("candidate-1"),
        FoldId("fold-1"),
    )
    return api.FoldPersistenceSpec.create(
        key=key,
        ordinal=ordinal,
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
    lease = _start_running_experiment(writer, owner=owner)
    writer.claim_fold_and_add_attempt(
        fold.key,
        _attempt_spec(api, fold.key),
        _attempt_projection(api),
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    return lease


def _claim_queued_experiment(
    writer: Any,
    *,
    owner: str,
    lease_until_epoch_us: int = NOW_US + 100,
) -> Any:
    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    assert queued.record.status is ExperimentStatus.QUEUED
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        owner,
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=lease_until_epoch_us,
    )
    assert lease is not None
    return lease


def _start_running_experiment(
    writer: Any,
    *,
    owner: str,
    lease_until_epoch_us: int = NOW_US + 100,
) -> Any:
    lease = _claim_queued_experiment(
        writer,
        owner=owner,
        lease_until_epoch_us=lease_until_epoch_us,
    )
    writer.transition_scheduled_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=1,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="experiment_started",
        detail={},
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


def _experiment_gate(
    api: SimpleNamespace,
    evaluation_id: str,
    experiment_id: str = "experiment-1",
) -> Any:
    return replace(
        _gate(api),
        evaluation_id=evaluation_id,
        experiment_id=ExperimentId(experiment_id),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        artifact_id=None,
    )


def _enqueue_fence(
    api: SimpleNamespace,
    *,
    gates: tuple[Any, ...] = (),
    folds: tuple[Any, ...] = (),
) -> Any:
    return api.ExperimentEnqueueFence.create(gates=gates, folds=folds)


def _current_enqueue_fence(
    writer: Any,
    experiment_id: ExperimentId = ExperimentId("experiment-1"),
) -> ExperimentEnqueueFence:
    reader = writer._reader
    return ExperimentEnqueueFence.create(
        gates=reader.list_gate_evaluations(experiment_id),
        folds=tuple(view.spec for view in reader.list_folds(experiment_id)),
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


def _insert_holdout_claim_fixture(
    database: Any, api: SimpleNamespace, claim: Any
) -> None:
    """Seed the frozen Task 7 table only for disposable schema-adversarial tests."""
    reason = api.canonical_payload(claim.selection_reason)
    database.get_connection().execute(
        """
        INSERT INTO holdout_claim(
            claim_id, research_cycle_id, research_cycle_hash, experiment_id,
            candidate_id, fold_id, fold_role, resolved_spec_hash, parameters_hash,
            snapshot_id, window_start, window_end, reproduction_fingerprint,
            logical_run_id, operator_confirmation, selection_reason_json,
            claim_payload_hash, claimed_at_epoch_us
        ) VALUES (?, ?, ?, ?, ?, ?, 'holdout', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            claim.claim_id,
            claim.cycle.cycle_id,
            str(claim.cycle.cycle_hash),
            str(claim.fold_key.experiment_id),
            str(claim.fold_key.candidate_id),
            str(claim.fold_key.fold_id),
            str(claim.resolved_spec_hash),
            str(claim.parameters_hash),
            str(claim.snapshot_id),
            claim.window.start.isoformat(),
            claim.window.end.isoformat(),
            str(claim.reproduction_fingerprint),
            claim.logical_run_id,
            claim.operator_confirmation,
            reason.json_bytes.decode("utf-8"),
            str(claim.claim_payload_hash),
            int(claim.claimed_at.timestamp() * 1_000_000),
        ),
    )
    database.get_connection().commit()


def _seed_all_tables(database: Any, writer: Any, api: SimpleNamespace) -> None:
    _create_experiment(writer, api)
    fold = _add_fold(writer, api, role="walk_forward")
    holdout_key = replace(fold.key, fold_id=FoldId("fold-holdout"))
    holdout = _fold_spec(api, key=holdout_key, role="holdout", ordinal=2)
    writer.add_fold(holdout, _fold_projection(api, holdout))
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-adversarial")
    writer.add_artifact(
        _artifact(api),
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        commit_guard=lambda: None,
    )
    writer.add_gate_evaluation(_gate(api))
    _insert_holdout_claim_fixture(
        database,
        api,
        _holdout_claim(api, holdout.key),
    )
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
    assert decoded.promotion_objective == _objective()


def test_launch_codec_rejects_schema_v1_payload_without_promotion_objective() -> None:
    api = _api()
    encoded = api.encode_launch_spec(_launch())
    decoded = orjson.loads(encoded.json_bytes)
    del decoded["promotion_objective"]
    legacy = api.canonical_payload(decoded)

    with pytest.raises(ExperimentSpecError) as exc_info:
        api.decode_launch_spec(legacy.json_bytes, legacy.content_hash)

    assert exc_info.value.details["reason_code"] == "invalid_canonical_payload"


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


@pytest.mark.parametrize("subject", ["gate", "fold"])
@pytest.mark.parametrize("mismatch", ["extra", "missing", "drift"])
def test_enqueue_exact_fence_rejects_child_set_mismatch_without_writes(
    tmp_path: Path,
    subject: str,
    mismatch: str,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    expected_gate = _experiment_gate(api, "preflight-gate-1")
    expected_fold = _fold_spec(api)
    fence_gates: tuple[Any, ...] = ()
    fence_folds: tuple[Any, ...] = ()
    if subject == "gate":
        fence_gates = (expected_gate,)
        if mismatch != "missing":
            writer.add_gate_evaluation(expected_gate)
        if mismatch == "extra":
            writer.add_gate_evaluation(_experiment_gate(api, "preflight-gate-extra"))
        elif mismatch == "drift":
            fence_gates = (replace(expected_gate, outcome="fail"),)
    else:
        fence_folds = (expected_fold,)
        if mismatch != "missing":
            writer.add_fold(expected_fold, _fold_projection(api, expected_fold))
        if mismatch == "extra":
            extra_key = api.FoldKey(
                ExperimentId("experiment-1"),
                CandidateId("candidate-2"),
                FoldId("fold-extra"),
            )
            extra = _fold_spec(api, key=extra_key, ordinal=2)
            writer.add_fold(extra, _fold_projection(api, extra))
        elif mismatch == "drift":
            fence_folds = (
                api.FoldPersistenceSpec.create(
                    key=expected_fold.key,
                    ordinal=expected_fold.ordinal,
                    fold_role=expected_fold.fold_role,
                    train_window=expected_fold.train_window,
                    test_window=expected_fold.test_window,
                    purge_sessions=expected_fold.purge_sessions + 1,
                    embargo_sessions=expected_fold.embargo_sessions,
                ),
            )
    fence = _enqueue_fence(api, gates=fence_gates, folds=fence_folds)
    before_projection = reader.get_experiment_projection(ExperimentId("experiment-1"))
    before_events = reader.list_status_events(ExperimentId("experiment-1"))
    before_changes = database.get_connection().total_changes

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.enqueue_experiment(
            ExperimentId("experiment-1"),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=fence,
        )

    assert exc_info.value.details["reason_code"] == (
        "enqueue_gate_fence_mismatch"
        if subject == "gate"
        else "enqueue_fold_fence_mismatch"
    )
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == (
        before_projection
    )
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events
    assert database.get_connection().total_changes == before_changes
    assert not database.get_connection().in_transaction


def test_enqueue_exact_fence_checks_hashes_and_cas_in_one_write_transaction(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    gate = _experiment_gate(api, "preflight-gate-1")
    fold = _fold_spec(api)
    writer.add_gate_evaluation(gate)
    writer.add_fold(fold, _fold_projection(api, fold))
    fence = _enqueue_fence(api, gates=(gate,), folds=(fold,))
    statements: list[str] = []
    connection = database.get_connection()
    connection.set_trace_callback(statements.append)

    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={"fenced": True},
        launch_fence=fence,
    )

    connection.set_trace_callback(None)
    normalized = tuple(statement.strip().upper() for statement in statements)
    begin = normalized.index("BEGIN IMMEDIATE")
    gate_read = next(
        index
        for index, statement in enumerate(normalized)
        if statement.startswith("SELECT * FROM GATE_EVALUATION")
    )
    fold_read = next(
        index
        for index, statement in enumerate(normalized)
        if statement.startswith("SELECT * FROM EXPERIMENT_FOLD")
    )
    root_update = next(
        index
        for index, statement in enumerate(normalized)
        if statement.startswith("UPDATE EXPERIMENT")
    )
    commit = normalized.index("COMMIT")
    assert begin < gate_read < fold_read < root_update < commit
    assert normalized.count("BEGIN IMMEDIATE") == 1
    assert normalized.count("COMMIT") == 1
    assert queued.record.status is ExperimentStatus.QUEUED
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == queued


def test_experiment_create_replay_after_enqueue_is_noop(tmp_path: Path) -> None:
    database, reader, writer, api = _store(tmp_path)
    cycle = api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64))
    spec = _launch()
    initial = _record()
    writer.create_experiment(cycle, spec, initial)
    queued = writer.enqueue_experiment(
        spec.experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer, spec.experiment_id),
    )
    before_events = reader.list_status_events(spec.experiment_id)
    before_changes = database.get_connection().total_changes

    writer.create_experiment(cycle, spec, initial)

    assert reader.get_experiment_projection(spec.experiment_id) == queued
    assert reader.list_status_events(spec.experiment_id) == before_events
    assert database.get_connection().total_changes == before_changes


def test_get_launch_spec_ignores_mutable_projection_intent_after_cancel_request(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    spec = _launch()
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64)),
        spec,
        _record(),
    )
    queued = writer.enqueue_experiment(
        spec.experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer, spec.experiment_id),
    )
    writer.transition_experiment(
        spec.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=ExperimentStage.PREFLIGHT,
        failure_code=None,
        expected_revision=queued.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancelled",
        detail={},
    )

    assert reader.get_launch_spec(spec.experiment_id) == spec


def test_get_launch_spec_rejects_relational_schema_version_drift(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    connection = database.get_connection()
    connection.execute("DROP TRIGGER trg_experiment_guard_update")
    connection.execute(
        "UPDATE experiment SET launch_spec_schema_version=2 WHERE experiment_id=?",
        ("experiment-1",),
    )
    connection.commit()

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        reader.get_launch_spec(ExperimentId("experiment-1"))

    assert exc_info.value.details["reason_code"] == "launch_schema_version_mismatch"


def test_get_launch_spec_requires_exact_revision_zero_creation_event(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    connection = database.get_connection()
    connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
    connection.execute(
        """
        UPDATE experiment_status_event SET reason_code='forged_creation'
        WHERE experiment_id='experiment-1' AND subject_type='experiment'
          AND subject_revision=0
        """
    )
    connection.commit()

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        reader.get_launch_spec(ExperimentId("experiment-1"))

    assert exc_info.value.details["reason_code"] == "launch_creation_event_drift"


def test_reader_recomputes_canonical_status_event_id(tmp_path: Path) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    connection = database.get_connection()
    connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
    connection.execute(
        """
        UPDATE experiment_status_event SET event_id='forged-id'
        WHERE event_id LIKE 'status:%'
        """
    )
    connection.commit()

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        reader.list_status_events(ExperimentId("experiment-1"))

    assert exc_info.value.details["reason_code"] == "status_event_id_mismatch"


def test_experiment_replay_requires_exact_revision_zero_event(tmp_path: Path) -> None:
    database, _reader, writer, api = _store(tmp_path)
    connection = database.get_connection()
    connection.execute(
        """
        CREATE TRIGGER ignore_experiment_creation_event
        BEFORE INSERT ON experiment_status_event
        WHEN NEW.subject_type='experiment' AND NEW.subject_revision=0
        BEGIN
            SELECT RAISE(IGNORE);
        END
        """
    )
    connection.commit()
    cycle = api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64))
    spec = _launch()
    initial = _record()
    writer.create_experiment(cycle, spec, initial)
    connection.execute("DROP TRIGGER ignore_experiment_creation_event")
    detail = api.canonical_payload({})
    connection.execute(
        """
        INSERT INTO experiment_status_event(
            event_id, experiment_id, candidate_id, fold_id, attempt_id,
            subject_type, subject_revision, previous_status, status,
            desired_state, stage, failure_code, reason_code, detail_json,
            detail_hash, occurred_at_epoch_us
        ) VALUES (?, ?, NULL, NULL, NULL, 'experiment', 0, NULL, 'draft',
                  'run', 'preflight', NULL, ?, ?, ?, ?)
        """,
        (
            "wrong-experiment-create-event",
            "experiment-1",
            "wrong_creation_reason",
            detail.json_bytes.decode("utf-8"),
            str(detail.content_hash),
            int(NOW.timestamp() * 1_000_000),
        ),
    )
    connection.commit()

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.create_experiment(cycle, spec, initial)

    assert exc_info.value.details["reason_code"] == "experiment_aggregate_replay_drift"


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
        ("experiment", 1),
        ("experiment", 2),
        ("fold", 0),
        ("fold", 1),
        ("attempt", 0),
    ]


def test_list_experiment_attempts_reads_all_folds_in_snapshot_order(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    first = _fold_spec(
        api,
        role="exploration",
        key=api.FoldKey(
            ExperimentId("experiment-1"),
            CandidateId("candidate-2"),
            FoldId("fold-first"),
        ),
        ordinal=1,
    )
    second = _fold_spec(
        api,
        role="exploration",
        key=api.FoldKey(
            ExperimentId("experiment-1"),
            CandidateId("candidate-1"),
            FoldId("fold-second"),
        ),
        ordinal=2,
    )
    for fold in (second, first):
        writer.add_fold(fold, _fold_projection(api, fold))
    lease = _start_running_experiment(writer, owner="owner-bulk-read")
    for ordinal, fold in enumerate((second, first), start=1):
        attempt_id = AttemptId(f"attempt-bulk-{ordinal}")
        spec = replace(
            _attempt_spec(api, fold.key),
            attempt_id=attempt_id,
        )
        projection = replace(_attempt_projection(api), attempt_id=attempt_id)
        writer.claim_fold_and_add_attempt(
            fold.key,
            spec,
            projection,
            expected_fold_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + ordinal + 1,
            occurred_at=NOW,
        )

    attempts = reader.list_experiment_attempts(ExperimentId("experiment-1"))

    assert tuple(attempt.spec.fold_key for attempt in attempts) == (
        first.key,
        second.key,
    )
    assert tuple(attempt.spec.attempt_id for attempt in attempts) == (
        AttemptId("attempt-bulk-2"),
        AttemptId("attempt-bulk-1"),
    )


def test_list_experiment_artifacts_reads_all_in_lineage_order(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api, role="walk_forward")
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-artifacts")
    lineage_artifact = _artifact(api)
    exempt_artifact = replace(
        _artifact(api),
        artifact_id="artifact-2",
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        artifact_kind="review_packet",
        relative_path="experiments/experiment-1/review_packet.json",
        content_hash=ContentHash("3" * 64),
    )
    for offset, artifact in enumerate((lineage_artifact, exempt_artifact)):
        writer.add_artifact(
            artifact,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 10 + offset,
            commit_guard=lambda: None,
        )

    listed = reader.list_experiment_artifacts(ExperimentId("experiment-1"))

    assert [record.artifact_id for record in listed] == ["artifact-2", "artifact-1"]
    assert listed[0] == reader.get_artifact("artifact-2")
    assert listed[1] == reader.get_artifact("artifact-1")
    assert reader.list_experiment_artifacts(ExperimentId("experiment-other")) == ()


def test_fold_create_replay_after_claim_is_noop(tmp_path: Path) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    initial = _fold_projection(api, fold)
    lease = _start_running_experiment(writer, owner="owner-replay")
    claimed = writer.claim_fold(
        fold.key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
    )
    before_events = reader.list_status_events(fold.key.experiment_id)
    before_changes = database.get_connection().total_changes

    writer.add_fold(fold, initial)

    assert reader.get_fold(fold.key).projection == claimed
    assert reader.list_status_events(fold.key.experiment_id) == before_events
    assert database.get_connection().total_changes == before_changes


def test_add_fold_rejects_new_insert_after_enqueue_without_writes(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    fold = _fold_spec(api)
    connection = database.get_connection()
    before_events = reader.list_status_events(fold.key.experiment_id)
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.add_fold(fold, _fold_projection(api, fold))

    assert exc_info.value.details == {
        "reason_code": "fold_creation_not_allowed",
        "status": ExperimentStatus.QUEUED.value,
        "desired_state": ExperimentDesiredState.RUN.value,
    }
    assert reader.get_fold(fold.key) is None
    assert reader.list_status_events(fold.key.experiment_id) == before_events
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


def test_terminal_transition_serializes_with_exact_fold_replay_but_rejects_new_fold(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    queued = writer.enqueue_experiment(
        fold.key.experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer, fold.key.experiment_id),
    )
    cancel_requested = writer.transition_experiment(
        fold.key.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=queued.record.stage,
        failure_code=None,
        expected_revision=queued.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    lease = writer.try_claim_lease(
        fold.key.experiment_id,
        "owner-drain",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    writer.transition_fold(
        fold.key,
        target_status=ExperimentStatus.CANCELLED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
        reason_code="cancel_queued_fold",
        detail={},
    )
    initial = _fold_projection(api, fold)
    barrier = Barrier(2)

    def terminalize() -> Any:
        barrier.wait()
        return writer.transition_scheduled_experiment(
            fold.key.experiment_id,
            target_status=ExperimentStatus.CANCELLED,
            target_stage=cancel_requested.record.stage,
            failure_code=None,
            expected_revision=cancel_requested.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="cancel_drained",
            detail={},
        )

    def replay() -> None:
        barrier.wait()
        writer.add_fold(fold, initial)

    with ThreadPoolExecutor(max_workers=2) as executor:
        terminal_future = executor.submit(terminalize)
        replay_future = executor.submit(replay)
        terminal = terminal_future.result()
        replay_future.result()

    assert terminal.record.status is ExperimentStatus.CANCELLED
    assert reader.get_fold(fold.key).projection.status is ExperimentStatus.CANCELLED
    assert len(reader.list_folds(fold.key.experiment_id)) == 1
    before_events = reader.list_status_events(fold.key.experiment_id)
    before_changes = database.get_connection().total_changes
    new_fold = _fold_spec(
        api,
        key=api.FoldKey(
            fold.key.experiment_id,
            fold.key.candidate_id,
            FoldId("fold-2"),
        ),
        ordinal=2,
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.add_fold(new_fold, _fold_projection(api, new_fold))

    assert exc_info.value.details == {
        "reason_code": "fold_creation_not_allowed",
        "status": ExperimentStatus.CANCELLED.value,
        "desired_state": ExperimentDesiredState.CANCEL.value,
    }
    assert reader.get_fold(new_fold.key) is None
    assert reader.list_status_events(fold.key.experiment_id) == before_events
    assert database.get_connection().total_changes == before_changes
    assert not database.get_connection().in_transaction


def test_new_fold_and_terminal_transition_serialize_without_terminal_live_child(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    cancel_requested = writer.transition_experiment(
        queued.record.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=queued.record.stage,
        failure_code=None,
        expected_revision=queued.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    lease = writer.try_claim_lease(
        queued.record.experiment_id,
        "owner-drain",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    fold = _fold_spec(api)
    initial = _fold_projection(api, fold)
    barrier = Barrier(2)

    def add_new_fold() -> tuple[str, str | None]:
        barrier.wait()
        try:
            writer.add_fold(fold, initial)
        except ExperimentSpecError as exc:
            return "rejected", exc.details["reason_code"]
        return "added", None

    def terminalize() -> tuple[str, str | None]:
        barrier.wait()
        try:
            writer.transition_scheduled_experiment(
                queued.record.experiment_id,
                target_status=ExperimentStatus.CANCELLED,
                target_stage=cancel_requested.record.stage,
                failure_code=None,
                expected_revision=cancel_requested.revision,
                lease_fence=lease.fence,
                now_epoch_us=NOW_US + 1,
                occurred_at=NOW,
                attempt_started=False,
                precondition_repairable=False,
                reason_code="cancel_drained",
                detail={},
            )
        except ExperimentSpecError as exc:
            return "rejected", exc.details["reason_code"]
        return "terminal", None

    with ThreadPoolExecutor(max_workers=2) as executor:
        add_future = executor.submit(add_new_fold)
        terminal_future = executor.submit(terminalize)
        add_result = add_future.result()
        terminal_result = terminal_future.result()

    parent = reader.get_experiment_projection(queued.record.experiment_id)
    persisted_fold = reader.get_fold(fold.key)
    assert not (
        parent.record.status is ExperimentStatus.CANCELLED
        and persisted_fold is not None
        and persisted_fold.projection.status is ExperimentStatus.QUEUED
    )
    if add_result[0] == "added":
        assert terminal_result == ("rejected", "experiment_live_child")
        assert parent.record.status is ExperimentStatus.CANCEL_REQUESTED
        assert persisted_fold is not None
    else:
        assert add_result == ("rejected", "fold_creation_not_allowed")
        assert terminal_result == ("terminal", None)
        assert parent.record.status is ExperimentStatus.CANCELLED
        assert persisted_fold is None


def test_fold_replay_requires_revision_zero_event(tmp_path: Path) -> None:
    database, _reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    connection = database.get_connection()
    connection.execute(
        """
        CREATE TRIGGER ignore_fold_creation_event
        BEFORE INSERT ON experiment_status_event
        WHEN NEW.subject_type='fold' AND NEW.subject_revision=0
        BEGIN
            SELECT RAISE(IGNORE);
        END
        """
    )
    connection.commit()
    fold = _fold_spec(api)
    initial = _fold_projection(api, fold)
    writer.add_fold(fold, initial)
    connection.execute("DROP TRIGGER ignore_fold_creation_event")
    connection.commit()

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.add_fold(fold, initial)

    assert exc_info.value.details["reason_code"] == "fold_aggregate_replay_drift"


def test_attempt_create_replay_after_completion_is_unfenced_noop(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _start_running_experiment(writer, owner="owner-replay")
    writer.claim_fold(
        fold.key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
    )
    spec = _attempt_spec(api, fold.key)
    initial = _attempt_projection(api)
    writer.add_attempt(
        spec,
        initial,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
    )
    running = writer.transition_attempt(
        spec.attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId("backtest-run-replay"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="attempt_started",
        detail={},
    )
    completed = writer.transition_attempt(
        spec.attempt_id,
        target_status=ExperimentStatus.COMPLETED,
        backtest_run_id=running.backtest_run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="attempt_completed",
        detail={},
    )
    writer.transition_fold(
        fold.key,
        target_status=ExperimentStatus.COMPLETED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=1,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="fold_completed",
        detail={},
    )
    before_events = reader.list_status_events(fold.key.experiment_id)
    before_changes = database.get_connection().total_changes

    writer.add_attempt(
        spec,
        initial,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 101,
    )

    assert reader.get_attempt(spec.attempt_id).projection == completed
    assert reader.list_status_events(fold.key.experiment_id) == before_events
    assert database.get_connection().total_changes == before_changes


def test_attempt_replay_requires_revision_zero_event(tmp_path: Path) -> None:
    database, _reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _start_running_experiment(writer, owner="owner-replay")
    writer.claim_fold(
        fold.key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
    )
    connection = database.get_connection()
    connection.execute(
        """
        CREATE TRIGGER ignore_attempt_creation_event
        BEFORE INSERT ON experiment_status_event
        WHEN NEW.subject_type='attempt' AND NEW.subject_revision=0
        BEGIN
            SELECT RAISE(IGNORE);
        END
        """
    )
    connection.commit()
    spec = _attempt_spec(api, fold.key)
    initial = _attempt_projection(api)
    writer.add_attempt(
        spec,
        initial,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
    )
    connection.execute("DROP TRIGGER ignore_attempt_creation_event")
    connection.commit()

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.add_attempt(
            spec,
            initial,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
        )

    assert exc_info.value.details["reason_code"] == "attempt_aggregate_replay_drift"


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

    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={"certified": True},
        launch_fence=_current_enqueue_fence(writer),
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
            target_status=ExperimentStatus.CANCEL_REQUESTED,
            target_desired_state=ExperimentDesiredState.CANCEL,
            target_stage=ExperimentStage.PREFLIGHT,
            failure_code=None,
            expected_revision=1,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="dispatch",
            detail={},
        )
    assert reader.get_experiment_projection(ExperimentId("experiment-1")).revision == 1
    assert len(reader.list_status_events(ExperimentId("experiment-1"))) == 2


def test_generic_transition_rejects_caller_supplied_queue_ordinal_before_write(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    before = reader.get_experiment_projection(ExperimentId("experiment-1"))
    before_events = reader.list_status_events(ExperimentId("experiment-1"))

    with pytest.raises(TypeError):
        writer.transition_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.QUEUED,
            target_desired_state=ExperimentDesiredState.RUN,
            target_stage=ExperimentStage.PREFLIGHT,
            failure_code=None,
            queue_ordinal=777,
            expected_revision=0,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="manual_queue_bypass",
            detail={},
        )

    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == before
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events


def test_generic_transition_rejects_scheduler_edge_without_fence_and_writes_nothing(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    before_events = reader.list_status_events(ExperimentId("experiment-1"))
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.RUNNING,
            target_desired_state=ExperimentDesiredState.RUN,
            target_stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            expected_revision=queued.revision,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="unfenced_dispatch",
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"] == "scheduler_transition_requires_fence"
    )
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == queued
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events
    assert reader.get_scheduler_slot() == before_slot


def test_typed_lineage_event_identity_does_not_collide_on_colons(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    candidates = (
        CandidateSpec(
            candidate_id=CandidateId("candidate:a"),
            ordinal=1,
            is_baseline=True,
            parameters={"lookback": 20},
        ),
        CandidateSpec(
            candidate_id=CandidateId("candidate"),
            ordinal=2,
            is_baseline=False,
            parameters={"lookback": 40},
        ),
    )
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64)),
        _launch(candidates=candidates),
        _record(),
    )
    keys = (
        api.FoldKey(
            ExperimentId("experiment-1"), CandidateId("candidate:a"), FoldId("b")
        ),
        api.FoldKey(
            ExperimentId("experiment-1"), CandidateId("candidate"), FoldId("a:b")
        ),
    )

    for ordinal, key in enumerate(keys, start=1):
        spec = _fold_spec(api, key=key, ordinal=ordinal)
        writer.add_fold(spec, _fold_projection(api, spec))

    fold_events = tuple(
        event
        for event in reader.list_status_events(ExperimentId("experiment-1"))
        if event.subject_type.value == "fold"
    )
    assert len(fold_events) == 2
    assert len({event.event_id for event in fold_events}) == 2


def test_status_events_order_numeric_revision_for_same_timestamp(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold)
    backtest_run_id = BacktestRunId("backtest-run-1")

    writer.transition_attempt(
        AttemptId("attempt-1"),
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=backtest_run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        reason_code="attempt_started",
        detail={},
    )
    for revision in range(1, 11):
        writer.transition_attempt(
            AttemptId("attempt-1"),
            target_status=ExperimentStatus.RUNNING,
            backtest_run_id=backtest_run_id,
            checkpoint_ref=CheckpointRef(f"checkpoint-{revision}"),
            failure_code=None,
            expected_revision=revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + revision + 2,
            occurred_at=NOW,
            reason_code="checkpoint",
            detail={},
        )

    revisions = tuple(
        event.subject_revision
        for event in reader.list_status_events(ExperimentId("experiment-1"))
        if event.attempt_id == AttemptId("attempt-1")
    )
    assert revisions == tuple(range(12))


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


def test_artifact_and_gate_are_typed_append_only_facts(tmp_path: Path) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    _add_fold(writer, api, role="holdout")
    lease = _claim_queued_experiment(writer, owner="owner-artifact")
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
        commit_guard=lambda: None,
    )
    pinned = writer.pin_artifact(
        "artifact-1",
        expected_revision=0,
        pinned_at=NOW,
        commit_guard=lambda: None,
    )
    assert pinned.is_pinned is True
    assert pinned.revision == 1
    with pytest.raises(api.ExperimentConflictError):
        writer.pin_artifact(
            "artifact-1",
            expected_revision=0,
            pinned_at=NOW,
            commit_guard=lambda: None,
        )

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


def test_application_writer_port_does_not_expose_unverified_artifact_mutations() -> (
    None
):
    from ditto_analysis.experiments.protocols import ExperimentWriterProtocol

    assert "add_artifact" not in ExperimentWriterProtocol.__dict__
    assert "pin_artifact" not in ExperimentWriterProtocol.__dict__


def test_list_gate_evaluations_returns_empty_for_experiment_without_gates(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)

    assert reader.list_gate_evaluations(ExperimentId("experiment-1")) == ()


def test_list_gate_evaluations_is_one_stable_experiment_scoped_read_transaction(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-other", ContentHash("e" * 64)),
        _launch(experiment_id="experiment-2"),
        _record("experiment-2"),
    )
    gate_z = _experiment_gate(api, "gate-z")
    gate_a = _experiment_gate(api, "gate-a")
    gate_other = _experiment_gate(api, "gate-m", "experiment-2")
    for gate in (gate_z, gate_other, gate_a):
        writer.add_gate_evaluation(gate)
    statements: list[str] = []
    connection = database.get_connection()
    connection.set_trace_callback(statements.append)

    actual = reader.list_gate_evaluations(ExperimentId("experiment-1"))

    connection.set_trace_callback(None)
    assert actual == (gate_a, gate_z)
    assert reader.list_gate_evaluations(ExperimentId("experiment-2")) == (gate_other,)
    normalized = tuple(statement.strip().upper() for statement in statements)
    assert normalized.count("BEGIN") == 1
    assert normalized.count("COMMIT") == 1
    assert (
        sum(
            statement.startswith("SELECT * FROM GATE_EVALUATION")
            for statement in normalized
        )
        == 1
    )


def test_list_gate_evaluations_fails_closed_on_tampered_payload(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    writer.add_gate_evaluation(_experiment_gate(api, "gate-tampered"))
    connection = database.get_connection()
    connection.execute("DROP TRIGGER trg_gate_evaluation_no_update")
    connection.execute(
        """
        UPDATE gate_evaluation SET observed_json='{"sessions": 61}'
        WHERE evaluation_id='gate-tampered'
        """
    )
    connection.commit()

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        reader.list_gate_evaluations(ExperimentId("experiment-1"))

    assert exc_info.value.details["reason_code"] == "gate_payload_hash_mismatch"


def test_artifact_create_exact_replay_after_pin_is_unfenced_noop(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    assert queued.record.status is ExperimentStatus.QUEUED
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-artifact",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 10,
    )
    assert lease is not None
    artifact = replace(
        _artifact(api),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
    )
    writer.add_artifact(
        artifact,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        commit_guard=lambda: None,
    )
    pinned = writer.pin_artifact(
        artifact.artifact_id,
        expected_revision=0,
        pinned_at=NOW,
        commit_guard=lambda: None,
    )
    before_changes = database.get_connection().total_changes

    writer.add_artifact(
        artifact,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 10,
        commit_guard=lambda: None,
    )

    assert reader.get_artifact(artifact.artifact_id) == pinned
    assert database.get_connection().total_changes == before_changes


def test_artifact_create_exact_replay_guard_failure_rolls_back_and_propagates(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    lease = _claim_queued_experiment(writer, owner="owner-artifact-replay-guard")
    artifact = replace(
        _artifact(api),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
    )
    writer.add_artifact(
        artifact,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        commit_guard=lambda: None,
    )
    guard_calls = 0

    def fail_guard() -> None:
        nonlocal guard_calls
        guard_calls += 1
        raise RuntimeError("artifact files changed before replay commit")

    with pytest.raises(
        RuntimeError, match="artifact files changed before replay commit"
    ):
        writer.add_artifact(
            artifact,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            commit_guard=fail_guard,
        )

    assert guard_calls == 1
    assert database.get_connection().in_transaction is False
    assert reader.get_artifact(artifact.artifact_id) == artifact


def test_artifact_create_drift_after_pin_fails_closed_before_lease_validation(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-artifact",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 10,
    )
    assert lease is not None
    artifact = replace(
        _artifact(api),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
    )
    writer.add_artifact(
        artifact,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        commit_guard=lambda: None,
    )
    pinned = writer.pin_artifact(
        artifact.artifact_id,
        expected_revision=0,
        pinned_at=NOW,
        commit_guard=lambda: None,
    )
    before_changes = database.get_connection().total_changes

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.add_artifact(
            replace(artifact, byte_size=artifact.byte_size + 1),
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 10,
            commit_guard=lambda: None,
        )

    assert exc_info.value.details["reason_code"] == "artifact_replay_drift"
    assert reader.get_artifact(artifact.artifact_id) == pinned
    assert database.get_connection().total_changes == before_changes


def test_holdout_claim_has_no_standalone_writer_bypass(tmp_path: Path) -> None:
    _database, _reader, writer, _api_values = _store(tmp_path)

    assert not hasattr(writer, "claim_holdout")


@pytest.mark.parametrize(
    "relative_path",
    ["/absolute/file", "../metadata/metadata.sqlite", "a/../b", "C:/drive", "a\\b"],
)
def test_artifact_path_validation_fails_before_sql(
    tmp_path: Path, relative_path: str
) -> None:
    _database, _reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    lease = _claim_queued_experiment(writer, owner="owner-artifact")
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
            commit_guard=lambda: None,
        )

    assert exc_info.value.details["reason_code"] == "invalid_artifact_relative_path"


def test_artifact_index_resolves_by_database_owned_canonical_root_and_path(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-artifact-root")
    artifact = _artifact(api)

    writer.add_artifact(
        artifact,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        commit_guard=lambda: None,
    )

    expected_root = (database.path.parent / "artifacts").resolve()
    assert database.artifact_root == expected_root
    assert reader.artifact_root == expected_root
    assert writer.artifact_root == expected_root
    assert reader.get_artifact_by_relative_path(artifact.relative_path) == artifact


@pytest.mark.parametrize(
    "mutated",
    [
        {"artifact_id": "artifact-other"},
        {"relative_path": "experiments/experiment-1/other.parquet"},
    ],
)
def test_artifact_id_or_path_conflict_is_typed_and_preserves_original(
    tmp_path: Path,
    mutated: dict[str, object],
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-artifact-key")
    original = _artifact(api)
    writer.add_artifact(
        original,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        commit_guard=lambda: None,
    )

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.add_artifact(
            replace(original, **mutated),
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 4,
            commit_guard=lambda: None,
        )

    assert exc_info.value.details["reason_code"] in {
        "artifact_path_identity_conflict",
        "artifact_replay_drift",
    }
    assert reader.get_artifact(original.artifact_id) == original


def test_artifact_id_and_path_cross_hit_two_rows_fails_closed(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-artifact-cross")
    first = _artifact(api)
    second = replace(
        first,
        artifact_id="artifact-2",
        relative_path="experiments/experiment-1/second.parquet",
        content_hash=ContentHash("3" * 64),
    )
    writer.add_artifact(
        first,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        commit_guard=lambda: None,
    )
    writer.add_artifact(
        second,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        commit_guard=lambda: None,
    )

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.add_artifact(
            replace(first, relative_path=second.relative_path),
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 5,
            commit_guard=lambda: None,
        )

    assert exc_info.value.details["reason_code"] == "artifact_identity_cross_conflict"
    assert reader.get_artifact(first.artifact_id) == first
    assert reader.get_artifact(second.artifact_id) == second


def test_indexed_service_publishes_to_the_database_owned_root(
    tmp_path: Path,
) -> None:
    from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
    from ditto_analysis.research.artifact_service import ResearchArtifactService

    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-artifact-file")
    relative_path = (
        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
        "attempts/attempt-1/result.json"
    )
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )

    record = service.publish_indexed_json(
        ArtifactPublicationSpec(
            artifact_id="artifact-file-1",
            experiment_id=ExperimentId("experiment-1"),
            candidate_id=CandidateId("candidate-1"),
            fold_id=FoldId("fold-1"),
            attempt_id=AttemptId("attempt-1"),
            artifact_kind="result",
            relative_path=relative_path,
            reproduction_fingerprint=ContentHash("d" * 64),
            audit={
                "run_id": "run-1",
                "attempt_id": "attempt-1",
                "created_at": NOW.isoformat(),
            },
            created_at=NOW,
        ),
        {"result": "ok"},
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
    )

    final_path = database.artifact_root / relative_path
    assert final_path.is_file()
    assert reader.get_artifact(record.artifact_id) == record
    assert service.read_indexed_json(record.artifact_id) == {"result": "ok"}


def test_committed_index_response_loss_replays_as_one_exact_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Callable

    from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
    from ditto_analysis.experiments.persistence import ArtifactRecord, LeaseFence
    from ditto_analysis.research.artifact_service import ResearchArtifactService

    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-response-loss")
    relative_path = (
        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
        "attempts/attempt-1/response.json"
    )
    spec = ArtifactPublicationSpec(
        artifact_id="artifact-response-loss",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId("attempt-1"),
        artifact_kind="response",
        relative_path=relative_path,
        reproduction_fingerprint=ContentHash("d" * 64),
        audit={
            "run_id": "run-response-loss",
            "attempt_id": "attempt-1",
            "created_at": NOW.isoformat(),
        },
        created_at=NOW,
    )
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    original_add = writer.add_artifact
    lost_once = False

    def commit_then_lose_response(
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        nonlocal lost_once
        original_add(
            record,
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
            commit_guard=commit_guard,
        )
        if not lost_once:
            lost_once = True
            raise api.ExperimentPersistenceError("injected response loss")

    monkeypatch.setattr(writer, "add_artifact", commit_then_lose_response)

    with pytest.raises(api.ExperimentPersistenceError, match="response loss"):
        service.publish_indexed_json(
            spec,
            {"result": "ok"},
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
        )

    committed = reader.get_artifact(spec.artifact_id)
    assert committed is not None
    replayed = service.publish_indexed_json(
        spec,
        {"result": "ok"},
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
    )
    assert replayed == committed
    count = (
        database.get_connection()
        .execute(
            "SELECT count(*) FROM research_artifact WHERE artifact_id=?",
            (spec.artifact_id,),
        )
        .fetchone()[0]
    )
    assert count == 1


def test_precommit_index_failure_repairs_exact_orphan_without_replacing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
    from ditto_analysis.research import _indexed_artifacts as artifact_module
    from ditto_analysis.research.artifact_service import ResearchArtifactService

    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-orphan-repair")
    relative_path = (
        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
        "attempts/attempt-1/orphan.json"
    )
    spec = ArtifactPublicationSpec(
        artifact_id="artifact-orphan-repair",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId("attempt-1"),
        artifact_kind="orphan",
        relative_path=relative_path,
        reproduction_fingerprint=ContentHash("d" * 64),
        audit={
            "run_id": "run-orphan-repair",
            "attempt_id": "attempt-1",
            "created_at": NOW.isoformat(),
        },
        created_at=NOW,
    )
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    original_add = writer.add_artifact

    def fail_before_transaction(*_args: object, **_kwargs: object) -> None:
        raise api.ExperimentPersistenceError("injected precommit failure")

    monkeypatch.setattr(writer, "add_artifact", fail_before_transaction)
    with pytest.raises(api.ExperimentPersistenceError, match="precommit failure"):
        service.publish_indexed_json(
            spec,
            {"result": "ok"},
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
        )

    target = database.artifact_root / relative_path
    sidecar = target.with_name(artifact_module._manifest_sidecar_name(target.name))
    before = (target.stat(), sidecar.stat())
    assert reader.get_artifact(spec.artifact_id) is None
    monkeypatch.setattr(writer, "add_artifact", original_add)

    repaired = service.publish_indexed_json(
        spec,
        {"result": "ok"},
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
    )

    after = (target.stat(), sidecar.stat())
    assert tuple((item.st_ino, item.st_mtime_ns) for item in after) == tuple(
        (item.st_ino, item.st_mtime_ns) for item in before
    )
    assert reader.get_artifact(spec.artifact_id) == repaired


def test_actual_sqlite_ports_reject_a_different_service_root(tmp_path: Path) -> None:
    from ditto_analysis.research.artifact_service import ResearchArtifactService

    database, reader, writer, _api_values = _store(tmp_path)

    with pytest.raises(ExperimentSpecError) as exc_info:
        ResearchArtifactService(
            artifact_root=tmp_path,
            indexed_artifact_root=database.artifact_root / "wrong",
            artifact_reader=reader,
            artifact_writer=writer,
        )

    assert exc_info.value.details["reason_code"] == "artifact_root_mismatch"
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM research_artifact")
        .fetchone()[0]
        == 0
    )


def test_parent_swap_inside_artifact_transaction_rolls_back_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
    from ditto_analysis.research.artifact_service import ResearchArtifactService

    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-artifact-race")
    relative_path = (
        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
        "attempts/attempt-1/result.json"
    )
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    original_validate = writer._validate_lease
    outside = tmp_path / "outside"
    outside.mkdir()
    swapped = False

    def validate_then_swap(*args: object, **kwargs: object) -> object:
        nonlocal swapped
        result = original_validate(*args, **kwargs)
        if not swapped:
            parent = database.artifact_root / Path(relative_path).parent
            moved = parent.with_name("attempt-1-original")
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        return result

    monkeypatch.setattr(writer, "_validate_lease", validate_then_swap)

    with pytest.raises(ExperimentSpecError) as exc_info:
        service.publish_indexed_json(
            ArtifactPublicationSpec(
                artifact_id="artifact-file-race",
                experiment_id=ExperimentId("experiment-1"),
                candidate_id=CandidateId("candidate-1"),
                fold_id=FoldId("fold-1"),
                attempt_id=AttemptId("attempt-1"),
                artifact_kind="result",
                relative_path=relative_path,
                reproduction_fingerprint=ContentHash("d" * 64),
                audit={
                    "run_id": "run-race",
                    "attempt_id": "attempt-1",
                    "created_at": NOW.isoformat(),
                },
                created_at=NOW,
            ),
            {"result": "ok"},
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
        )

    assert exc_info.value.details["reason_code"] == "artifact_path_race_detected"
    assert reader.get_artifact("artifact-file-race") is None
    assert not database.get_connection().in_transaction
    assert tuple(outside.iterdir()) == ()


def test_parent_swap_inside_pin_transaction_rolls_back_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Callable

    from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
    from ditto_analysis.experiments.persistence import ArtifactRecord
    from ditto_analysis.research.artifact_service import ResearchArtifactService

    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    fold = _add_fold(writer, api)
    lease = _dispatch_first_attempt(writer, api, fold, owner="owner-pin-race")
    relative_path = (
        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
        "attempts/attempt-1/result.json"
    )
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    record = service.publish_indexed_json(
        ArtifactPublicationSpec(
            artifact_id="artifact-pin-race",
            experiment_id=ExperimentId("experiment-1"),
            candidate_id=CandidateId("candidate-1"),
            fold_id=FoldId("fold-1"),
            attempt_id=AttemptId("attempt-1"),
            artifact_kind="result",
            relative_path=relative_path,
            reproduction_fingerprint=ContentHash("d" * 64),
            audit={
                "run_id": "run-pin-race",
                "attempt_id": "attempt-1",
                "created_at": NOW.isoformat(),
            },
            created_at=NOW,
        ),
        {"result": "ok"},
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
    )
    original_pin = writer.pin_artifact
    outside = tmp_path / "outside-pin"
    outside.mkdir()

    def pin_with_swap(
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        def swap_then_guard() -> None:
            parent = database.artifact_root / Path(relative_path).parent
            moved = parent.with_name("attempt-1-original")
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
            commit_guard()

        return original_pin(
            artifact_id,
            expected_revision=expected_revision,
            pinned_at=pinned_at,
            commit_guard=swap_then_guard,
        )

    monkeypatch.setattr(writer, "pin_artifact", pin_with_swap)

    with pytest.raises(ExperimentSpecError) as exc_info:
        service.pin_indexed_artifact(
            record.artifact_id,
            expected_revision=0,
            pinned_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "artifact_path_race_detected"
    persisted = reader.get_artifact(record.artifact_id)
    assert persisted is not None
    assert persisted.is_pinned is False
    assert persisted.pinned_at is None
    assert persisted.revision == 0
    assert not database.get_connection().in_transaction
    assert tuple(outside.iterdir()) == ()


def test_list_experiments_returns_every_seeded_root_newest_first(
    tmp_path: Path,
) -> None:
    """list_experiments projects every experiment row, newest first."""
    _, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    seeded = reader.get_experiment_projection(ExperimentId("experiment-1"))
    assert seeded is not None

    result = reader.list_experiments()

    assert result == (seeded,)


def _review_packet() -> Any:
    """Construct one review packet for persistence tests (no assemble_review_packet)."""
    from ditto_analysis.experiments.evidence import (
        REVIEW_PACKET_SCHEMA_VERSION,
        ReviewPacket,
        ReviewPacketLineage,
    )
    from ditto_analysis.experiments.gates import GateEvaluation, GateLayer, GateOutcome

    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_ids=("fold-1",),
            attempt_ids=("attempt-1",),
        ),
        spec_hash=ContentHash("a" * 64),
        resolved_spec_hash=ContentHash("b" * 64),
        parameter_hash=ContentHash("c" * 64),
        snapshot_hash=ContentHash("d" * 64),
        registry_hash=ContentHash("e" * 64),
        objective_payload_hash=ContentHash("f" * 64),
        gate_evaluations=(
            GateEvaluation(
                rule_id="certified_snapshot",
                layer=GateLayer.HARD,
                outcome=GateOutcome.PASS,
                observed="verified",
                policy={"required": True},
            ),
        ),
        comparison_payload_hash=ContentHash("9" * 64),
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id=None,
        holdout_claim_id=None,
        candidate_rationale="Captures durable net return after costs.",
    )


def test_publish_review_packet_round_trips_through_bundle_hash(
    tmp_path: Path,
) -> None:
    """ReviewPacket persists content-addressed and reloads via bundle hash."""
    from ditto_analysis.experiments.persistence import LeaseFence

    _, reader, writer, _api = _store(tmp_path)
    _create_experiment(writer, _api)
    packet = _review_packet()
    fence = LeaseFence(
        experiment_id=ExperimentId("experiment-1"),
        owner_token="promotion-owner",
        revision=0,
        lease_until_epoch_us=NOW_US + 100,
    )

    record = writer.publish_review_packet(
        packet,
        lease_fence=fence,
        now_epoch_us=NOW_US + 1,
        created_at=NOW,
    )

    assert record.artifact_kind == "review_packet"
    assert str(record.reproduction_fingerprint) == str(packet.bundle_hash)

    restored = reader.get_review_packet(str(packet.bundle_hash))
    assert restored is not None
    assert restored == packet
    assert reader.get_review_packet("0" * 64) is None


def test_get_review_packet_for_experiment_round_trips_by_lineage(
    tmp_path: Path,
) -> None:
    """ReviewPacket reloads via experiment_id lineage identity."""
    from ditto_analysis.experiments.persistence import LeaseFence

    _, reader, writer, _api = _store(tmp_path)
    _create_experiment(writer, _api)
    packet = _review_packet()
    fence = LeaseFence(
        experiment_id=ExperimentId("experiment-1"),
        owner_token="promotion-owner",
        revision=0,
        lease_until_epoch_us=NOW_US + 100,
    )
    writer.publish_review_packet(
        packet,
        lease_fence=fence,
        now_epoch_us=NOW_US + 1,
        created_at=NOW,
    )

    restored = reader.get_review_packet_for_experiment(ExperimentId("experiment-1"))
    assert restored is not None
    assert restored == packet
    assert reader.get_review_packet_for_experiment(ExperimentId("missing")) is None


def test_get_experiment_id_by_spec_hash_resolves_only_when_packet_exists(
    tmp_path: Path,
) -> None:
    """spec_hash bridge resolves the experiment owning a persisted review packet."""
    from ditto_analysis.experiments.persistence import LeaseFence

    _, reader, writer, _api = _store(tmp_path)
    _create_experiment(writer, _api)
    # Experiment exists (strategy_spec_hash="a"*64) but has no review packet yet.
    assert reader.get_experiment_id_by_spec_hash("a" * 64) is None
    # Unknown spec hash never resolves.
    assert reader.get_experiment_id_by_spec_hash("0" * 64) is None

    packet = _review_packet()
    fence = LeaseFence(
        experiment_id=ExperimentId("experiment-1"),
        owner_token="promotion-owner",
        revision=0,
        lease_until_epoch_us=NOW_US + 100,
    )
    writer.publish_review_packet(
        packet,
        lease_fence=fence,
        now_epoch_us=NOW_US + 1,
        created_at=NOW,
    )

    # Now the packet exists → the spec hash resolves to its experiment.
    assert reader.get_experiment_id_by_spec_hash("a" * 64) == ExperimentId(
        "experiment-1"
    )


def test_publish_review_packet_does_not_require_active_lease(tmp_path: Path) -> None:
    """ReviewPacket is a post-execution governance artifact; lease is exempt."""
    from ditto_analysis.experiments.persistence import LeaseFence

    _, reader, writer, _api = _store(tmp_path)
    _create_experiment(writer, _api)
    packet = _review_packet()
    stale_fence = LeaseFence(
        experiment_id=ExperimentId("experiment-1"),
        owner_token="promotion-owner",
        revision=0,
        lease_until_epoch_us=NOW_US - 1,
    )

    record = writer.publish_review_packet(
        packet,
        lease_fence=stale_fence,
        now_epoch_us=NOW_US,
        created_at=NOW,
    )

    assert record.artifact_kind == "review_packet"
    assert reader.get_review_packet(str(packet.bundle_hash)) == packet


def test_publish_review_packet_rejects_legacy_v1_before_file_or_index_write(
    tmp_path: Path,
) -> None:
    """Schema v1 remains readable history and cannot be newly published."""
    from ditto_analysis.experiments.evidence import REVIEW_PACKET_SCHEMA_VERSION_V1
    from ditto_analysis.experiments.persistence import LeaseFence

    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    packet = replace(
        _review_packet(),
        schema_version=REVIEW_PACKET_SCHEMA_VERSION_V1,
    )
    fence = LeaseFence(
        experiment_id=ExperimentId("experiment-1"),
        owner_token="promotion-owner",
        revision=0,
        lease_until_epoch_us=NOW_US + 100,
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.publish_review_packet(
            packet,
            lease_fence=fence,
            now_epoch_us=NOW_US + 1,
            created_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "review_packet_schema_read_only"
    assert reader.get_review_packet(str(packet.bundle_hash)) is None
    assert not (
        database.artifact_root
        / f"experiments/{packet.lineage.experiment_id}/review-packet.json"
    ).exists()


def test_reader_reopens_low_level_seeded_legacy_v1_packet(tmp_path: Path) -> None:
    """Simulate an existing v1 artifact without using the now-v2-only writer."""
    from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
    from ditto_analysis.experiments.evidence import REVIEW_PACKET_SCHEMA_VERSION_V1
    from ditto_analysis.experiments.persistence import LeaseFence
    from ditto_analysis.research._indexed_artifacts import IndexedArtifactIO

    database, reader, writer, api = _store(tmp_path)
    _create_experiment(writer, api)
    packet = replace(
        _review_packet(),
        schema_version=REVIEW_PACKET_SCHEMA_VERSION_V1,
    )
    bundle_hash = packet.bundle_hash
    spec = ArtifactPublicationSpec(
        artifact_id=f"review-packet-{bundle_hash}",
        experiment_id=ExperimentId(packet.lineage.experiment_id),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        artifact_kind="review_packet",
        relative_path=(
            f"experiments/{packet.lineage.experiment_id}/review-packet.json"
        ),
        reproduction_fingerprint=bundle_hash,
        audit={"created_at": NOW.isoformat()},
        created_at=NOW,
    )
    fence = LeaseFence(
        experiment_id=ExperimentId("experiment-1"),
        owner_token="legacy-seed",
        revision=0,
        lease_until_epoch_us=NOW_US - 1,
    )
    indexed = IndexedArtifactIO(
        artifact_root=database.artifact_root,
        reader=reader,
        writer=writer,
    )

    indexed.publish_json(
        spec,
        packet.canonical_payload(),
        lease_fence=fence,
        now_epoch_us=NOW_US,
    )

    restored = reader.get_review_packet(str(bundle_hash))
    assert restored == packet
    assert restored is not None
    assert restored.canonical_payload() == packet.canonical_payload()
