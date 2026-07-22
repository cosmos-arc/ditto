"""Fresh-tmp SQLite integration for the Task 9 durable scheduler seam."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldProtocolSpec,
    FoldRole,
    FoldView,
    LogicalTrialIdentity,
    ResearchCycleIdentity,
    ResearchMetricDirection,
    ResearchMetricId,
    SnapshotId,
    StrategyVersion,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.trial_ledger import (
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    SchedulerTickState,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttempt,
)

NOW = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)


class _Factory:
    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        attempt_id = AttemptId(
            f"attempt-{fold.spec.key.experiment_id}-"
            f"{fold.spec.key.candidate_id}-{fold.spec.key.fold_id}"
        )
        spec = AttemptPersistenceSpec(
            attempt_id,
            fold.spec.key,
            1,
            None,
            None,
            ContentHash("f" * 64),
            occurred_at,
        )
        projection = AttemptProjection(
            attempt_id,
            ExperimentStatus.QUEUED,
            None,
            None,
            None,
            occurred_at,
            occurred_at,
            0,
        )
        return FirstAttempt(spec, projection)


def _launch(
    experiment_id: str = "experiment-scheduler-integration",
    *,
    candidate_count: int = 3,
) -> ExperimentLaunchSpec:
    candidates = tuple(
        CandidateSpec(
            CandidateId(f"candidate-{ordinal}"),
            ordinal,
            ordinal == 1,
            {"value": ordinal},
        )
        for ordinal in range(1, candidate_count + 1)
    )
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId(experiment_id),
        strategy_version=StrategyVersion("strategy@integration"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-integration"),
        candidates=candidates,
        execution_bindings=tuple(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash(f"{candidate.ordinal + 16:064x}"),
            )
            for candidate in candidates
        ),
        promotion_objective=PromotionObjective(
            ObjectiveMetric(
                ResearchMetricId.NET_RETURN,
                ResearchMetricDirection.MAXIMIZE,
            ),
            (),
            (),
            CandidateId("candidate-1"),
            "Test durable scheduler behavior.",
            TrialFamilyDeclaration(
                "scheduler-test-family",
                tuple(
                    LogicalTrialIdentity(
                        ExperimentId(experiment_id),
                        candidate.candidate_id,
                        candidate.ordinal,
                        candidate.parameter_hash,
                        TrialKind.CURRENT,
                    )
                    for candidate in candidates
                ),
            ),
        ),
        fold_protocol=FoldProtocolSpec("r3", 1, ContentHash("b" * 64)),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 512),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _folds(spec: ExperimentLaunchSpec) -> tuple[FoldPersistenceSpec, ...]:
    folds: list[FoldPersistenceSpec] = []
    for candidate in spec.candidates:
        for ordinal, role in (
            (1, FoldRole.EXPLORATION),
            (2, FoldRole.WALK_FORWARD),
            (3, FoldRole.WALK_FORWARD),
            (4, FoldRole.HOLDOUT),
        ):
            key = FoldKey(
                spec.experiment_id,
                candidate.candidate_id,
                FoldId(f"fold-{candidate.ordinal}-{ordinal}"),
            )
            train = (
                None
                if role is FoldRole.EXPLORATION
                else DateWindow(date(2020, 1, 1), date(2024, 12, 31))
            )
            folds.append(
                FoldPersistenceSpec.create(
                    key,
                    ordinal,
                    role,
                    train,
                    DateWindow(date(2025, ordinal, 1), date(2025, ordinal, 28)),
                    2,
                    1,
                )
            )
    return tuple(folds)


def _store(
    tmp_path: Path,
) -> tuple[
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    ExperimentSchedulerStore,
]:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    launch = _launch()
    _persist_enqueued(writer, launch, cycle_id="cycle-integration")
    return database, reader, ExperimentSchedulerStore(reader, writer)


def _persist_enqueued(
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    *,
    cycle_id: str,
) -> None:
    writer.create_experiment(
        ResearchCycleIdentity(cycle_id, ContentHash("c" * 64)),
        launch,
        ExperimentRecord(
            launch.experiment_id,
            ExperimentStatus.DRAFT,
            ExperimentDesiredState.RUN,
            ExperimentStage.PREFLIGHT,
            NOW,
        ),
    )
    folds = _folds(launch)
    for fold in folds:
        writer.add_fold(
            fold,
            FoldProjection(
                fold.key,
                ExperimentStatus.QUEUED,
                None,
                NOW,
                NOW,
                0,
            ),
        )
    writer.enqueue_experiment(
        launch.experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=ExperimentEnqueueFence.create(gates=(), folds=folds),
    )


def test_sqlite_tick_claims_capacity_once_and_second_owner_stays_out(
    tmp_path: Path,
) -> None:
    database, reader, store = _store(tmp_path)
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_Factory(),
        owner_token="integration-owner-a",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    other = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_Factory(),
        owner_token="integration-owner-b",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(seconds=3),
    )

    first = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    repeated = coordinator.tick(occurred_at=NOW + timedelta(seconds=2))
    blocked = other.tick(occurred_at=NOW + timedelta(seconds=3))

    assert first.state is SchedulerTickState.DISPATCHED
    assert len(first.dispatches) == 2
    assert repeated.state is SchedulerTickState.WAITING
    assert repeated.dispatches == ()
    assert blocked.state is SchedulerTickState.LEASE_BUSY
    assert (
        sum(
            len(reader.list_attempts(fold.spec.key))
            for fold in reader.list_folds(_launch().experiment_id)
        )
        == 2
    )
    assert (
        sum(
            fold.projection.status is ExperimentStatus.RUNNING
            for fold in reader.list_folds(_launch().experiment_id)
        )
        == 2
    )
    database.close_all()


def test_scheduler_snapshot_reads_attempts_in_one_query_at_candidate_limit(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    launch = _launch(candidate_count=128)
    _persist_enqueued(writer, launch, cycle_id="cycle-query-count")
    store = ExperimentSchedulerStore(reader, writer)
    statements: list[str] = []
    connection = database.get_connection()
    connection.set_trace_callback(statements.append)

    snapshot = store.load_snapshot(launch.experiment_id)

    connection.set_trace_callback(None)
    attempt_selects = tuple(
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
        and "FROM EXPERIMENT_ATTEMPT" in " ".join(statement.upper().split())
    )
    assert len(snapshot.folds) == 512
    assert snapshot.attempts == ()
    assert len(attempt_selects) == 1
    database.close_all()


def test_scheduler_snapshot_rejects_attempt_whose_fold_is_missing(
    tmp_path: Path,
) -> None:
    database, _reader, store = _store(tmp_path)
    connection = database.get_connection()
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute(
        """
        INSERT INTO experiment_attempt(
            attempt_id, experiment_id, candidate_id, fold_id, ordinal,
            parent_attempt_id, status, backtest_run_id, resume_from_run_id,
            checkpoint_ref, reproduction_fingerprint, failure_code,
            created_at_epoch_us, updated_at_epoch_us, revision
        ) VALUES (?, ?, ?, ?, 1, NULL, 'queued', NULL, NULL, NULL, ?, NULL, ?, ?, 0)
        """,
        (
            "attempt-orphaned-fold",
            str(_launch().experiment_id),
            "candidate-1",
            "fold-missing",
            "f" * 64,
            int(NOW.timestamp() * 1_000_000),
            int(NOW.timestamp() * 1_000_000),
        ),
    )
    connection.commit()
    connection.execute("PRAGMA foreign_keys=ON")

    with pytest.raises(AppProcessError) as exc_info:
        store.load_snapshot(_launch().experiment_id)

    assert exc_info.value.details["reason"] == (
        "scheduler_snapshot_attempt_lineage_invalid"
    )
    database.close_all()


def test_expired_terminal_occupant_hands_slot_to_current_queue_head(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    terminal = _launch("experiment-terminal-occupant")
    successor = _launch("experiment-queue-successor")
    _persist_enqueued(writer, terminal, cycle_id="cycle-terminal")
    _persist_enqueued(writer, successor, cycle_id="cycle-successor")
    claim_now = int((NOW + timedelta(seconds=1)).timestamp() * 1_000_000)
    lease = writer.try_claim_lease(
        terminal.experiment_id,
        "terminal-owner",
        expected_revision=0,
        now_epoch_us=claim_now,
        lease_until_epoch_us=claim_now + 1_000_000,
    )
    assert lease is not None
    running = writer.transition_scheduled_experiment(
        terminal.experiment_id,
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=1,
        lease_fence=lease.fence,
        now_epoch_us=claim_now,
        occurred_at=NOW + timedelta(seconds=1),
        attempt_started=False,
        precondition_repairable=False,
        reason_code="scheduler_dispatch",
        detail={},
    )
    for fold in reader.list_folds(terminal.experiment_id):
        writer.transition_fold(
            fold.spec.key,
            target_status=ExperimentStatus.CANCELLED,
            claim_owner_token=None,
            failure_code=None,
            expected_revision=fold.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=claim_now,
            occurred_at=NOW + timedelta(seconds=1),
            reason_code="terminal_handoff_fixture",
            detail={},
        )
    writer.transition_scheduled_experiment(
        terminal.experiment_id,
        target_status=ExperimentStatus.FAILED,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        expected_revision=running.revision,
        lease_fence=lease.fence,
        now_epoch_us=claim_now,
        occurred_at=NOW + timedelta(seconds=1),
        attempt_started=True,
        precondition_repairable=False,
        reason_code="system_failure",
        detail={},
    )
    coordinator = ExperimentExecutionCoordinator(
        store=ExperimentSchedulerStore(reader, writer),
        first_attempt_factory=_Factory(),
        owner_token="successor-owner",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(seconds=3),
    )

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=3))

    assert result.state is SchedulerTickState.DISPATCHED
    assert result.experiment_id == successor.experiment_id
    assert {item.fold.spec.key.experiment_id for item in result.dispatches} == {
        successor.experiment_id
    }
    database.close_all()
