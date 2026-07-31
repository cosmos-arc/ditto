"""Fresh-tmp SQLite integration for Task 10 control and crash recovery."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    CheckpointRef,
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
    SchedulerLease,
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
from ditto_application.mutation_idempotency import (
    build_mutation_idempotency,
    canonical_resource_id,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    SchedulerTickState,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentExecutionControlChanged,
    ExperimentSchedulerStore,
    ExperimentSchedulerStoreProtocol,
    FirstAttempt,
    QueuedAttempt,
    ResearchExecutionDirective,
)

NOW = datetime(2026, 7, 22, 2, 0, tzinfo=UTC)


class _RecoveryFactory:
    """Create deterministic attempts while preserving the immutable lineage."""

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        spec, projection = self._attempt(
            fold,
            ordinal=1,
            parent=None,
            occurred_at=occurred_at,
        )
        return FirstAttempt(spec, projection)

    def create_successor(
        self,
        fold: FoldView,
        parent: AttemptView,
        *,
        resume_from_run_id: BacktestRunId | None,
        occurred_at: datetime,
    ) -> QueuedAttempt:
        spec, projection = self._attempt(
            fold,
            ordinal=parent.spec.ordinal + 1,
            parent=parent,
            resume_from_run_id=resume_from_run_id,
            occurred_at=occurred_at,
        )
        return QueuedAttempt(spec, projection)

    @staticmethod
    def _attempt(
        fold: FoldView,
        *,
        ordinal: int,
        parent: AttemptView | None,
        resume_from_run_id: BacktestRunId | None = None,
        occurred_at: datetime,
    ) -> tuple[AttemptPersistenceSpec, AttemptProjection]:
        attempt_id = AttemptId(
            f"attempt-{fold.spec.key.experiment_id}-"
            f"{fold.spec.key.candidate_id}-{fold.spec.key.fold_id}-{ordinal}"
        )
        fingerprint = (
            ContentHash("f" * 64)
            if parent is None
            else parent.spec.reproduction_fingerprint
        )
        spec = AttemptPersistenceSpec(
            attempt_id,
            fold.spec.key,
            ordinal,
            None if parent is None else parent.spec.attempt_id,
            resume_from_run_id,
            fingerprint,
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
        return spec, projection


def _launch(experiment_id: str) -> ExperimentLaunchSpec:
    candidate = CandidateSpec(CandidateId("candidate-1"), 1, True, {})
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId(experiment_id),
        strategy_version=StrategyVersion("strategy@recovery-integration"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-recovery-integration"),
        candidates=(candidate,),
        execution_bindings=(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash("2" * 64),
            ),
        ),
        promotion_objective=PromotionObjective(
            ObjectiveMetric(
                ResearchMetricId.NET_RETURN,
                ResearchMetricDirection.MAXIMIZE,
            ),
            (),
            (),
            CandidateId("candidate-1"),
            "Test deterministic recovery behavior.",
            TrialFamilyDeclaration(
                "recovery-test-family",
                (
                    LogicalTrialIdentity(
                        ExperimentId(experiment_id),
                        candidate.candidate_id,
                        candidate.ordinal,
                        candidate.parameter_hash,
                        TrialKind.CURRENT,
                    ),
                ),
            ),
        ),
        fold_protocol=FoldProtocolSpec("r3", 1, ContentHash("b" * 64)),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(32, 128),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _folds(spec: ExperimentLaunchSpec) -> tuple[FoldPersistenceSpec, ...]:
    roles = (
        FoldRole.EXPLORATION,
        FoldRole.WALK_FORWARD,
        FoldRole.WALK_FORWARD,
        FoldRole.HOLDOUT,
    )
    return tuple(
        FoldPersistenceSpec.create(
            FoldKey(
                spec.experiment_id,
                CandidateId("candidate-1"),
                FoldId(f"fold-1-{ordinal}"),
            ),
            ordinal,
            role,
            (
                None
                if role is FoldRole.EXPLORATION
                else DateWindow(date(2020, 1, 1), date(2024, 12, 31))
            ),
            DateWindow(date(2025, ordinal, 1), date(2025, ordinal, 28)),
            2,
            1,
        )
        for ordinal, role in enumerate(roles, start=1)
    )


def _persist_enqueued(
    writer: SQLiteExperimentWriter,
    spec: ExperimentLaunchSpec,
) -> None:
    writer.create_experiment(
        ResearchCycleIdentity(
            f"cycle-{spec.experiment_id}",
            ContentHash("c" * 64),
        ),
        spec,
        ExperimentRecord(
            spec.experiment_id,
            ExperimentStatus.DRAFT,
            ExperimentDesiredState.RUN,
            ExperimentStage.PREFLIGHT,
            NOW,
        ),
    )
    folds = _folds(spec)
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
        spec.experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=ExperimentEnqueueFence.create(gates=(), folds=folds),
    )


def _setup(
    tmp_path: Path,
    experiment_id: str,
) -> tuple[
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    ExperimentLaunchSpec,
]:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    launch = _launch(experiment_id)
    _persist_enqueued(SQLiteExperimentWriter(database), launch)
    return database, reader, launch


def _store(database: ResearchExperimentDatabase) -> ExperimentSchedulerStore:
    return ExperimentSchedulerStore(
        SQLiteExperimentReader(database),
        SQLiteExperimentWriter(database),
    )


def _coordinator(
    database: ResearchExperimentDatabase,
    *,
    owner: str,
    clock: datetime,
    checkpoints: set[str] | None = None,
    resumable_checkpoints: set[str] | None = None,
    lease_duration: timedelta = timedelta(seconds=5),
    scheduler_store: ExperimentSchedulerStoreProtocol | None = None,
) -> ExperimentExecutionCoordinator:
    available = set() if checkpoints is None else checkpoints
    resumable = set() if resumable_checkpoints is None else resumable_checkpoints
    return ExperimentExecutionCoordinator(
        store=_store(database) if scheduler_store is None else scheduler_store,
        first_attempt_factory=_RecoveryFactory(),
        owner_token=owner,
        lease_duration=lease_duration,
        clock=lambda: clock,
        checkpoint_available=available.__contains__,
        checkpoint_resumable=resumable.__contains__,
    )


class _PostWriteRetryStore:
    """Pause retry return after its SQLite commit to expose readback races."""

    def __init__(
        self,
        delegate: ExperimentSchedulerStore,
        post_write_barrier: Barrier,
    ) -> None:
        self._delegate = delegate
        self._post_write_barrier = post_write_barrier

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def retry_terminal_fold(
        self,
        fold: FoldView,
        parent_attempt: AttemptView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object] | None = None,
    ) -> FoldView:
        persisted = self._delegate.retry_terminal_fold(
            fold,
            parent_attempt,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            detail=detail,
        )
        self._post_write_barrier.wait(timeout=5)
        self._post_write_barrier.wait(timeout=5)
        return persisted


def _live_attempt_count(
    database: ResearchExperimentDatabase,
    experiment_id: ExperimentId,
) -> int:
    row = (
        database.get_connection()
        .execute(
            """
        SELECT count(*)
        FROM experiment_attempt
        WHERE experiment_id=? AND status IN ('queued', 'running')
        """,
            (str(experiment_id),),
        )
        .fetchone()
    )
    assert row is not None
    return int(row[0])


def test_pause_receipt_replays_after_coordinator_restart_without_second_event(
    tmp_path: Path,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-pause-idempotency")
    coordinator = _coordinator(
        database,
        owner="pause-first-owner",
        clock=NOW + timedelta(seconds=1),
    )
    coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    current = reader.get_experiment_projection(launch.experiment_id)
    assert current is not None
    expected_revision = current.revision
    identity = build_mutation_idempotency(
        operation_id="research_pause_experiment",
        resource_id=canonical_resource_id(
            "experiment",
            {"experiment_id": str(launch.experiment_id)},
        ),
        raw_key="pause-integration-001",
        request_payload={"expected_revision": expected_revision},
    )
    first = coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=expected_revision,
        occurred_at=NOW + timedelta(seconds=1),
        idempotency=identity,
    )
    event_count = len(reader.list_status_events(launch.experiment_id))

    replay = _coordinator(
        database,
        owner="pause-restarted-owner",
        clock=NOW + timedelta(seconds=2),
    ).pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=expected_revision,
        occurred_at=NOW + timedelta(seconds=2),
        idempotency=identity,
    )

    assert replay == first
    assert replay.replayed is True
    assert len(reader.list_status_events(launch.experiment_id)) == event_count
    assert "pause-integration-001" not in repr(
        reader.list_status_events(launch.experiment_id)
    )
    database.close_all()


@pytest.mark.parametrize("parent_started", [False, True])
def test_expired_lease_takeover_reclaims_and_dispatches_exactly_one_successor(
    tmp_path: Path,
    parent_started: bool,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-crash-takeover")
    first_owner = _coordinator(
        database,
        owner="owner-a",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(seconds=2),
    )
    first_tick = first_owner.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = first_tick.dispatches[0].attempt
    if parent_started:
        parent = first_owner.start_attempt(
            first_tick.dispatches[0],
            occurred_at=NOW + timedelta(seconds=2),
        ).attempt
    recovering_owner = _coordinator(
        database,
        owner="owner-b",
        clock=NOW + timedelta(seconds=10),
    )

    recovered = recovering_owner.tick(occurred_at=NOW + timedelta(seconds=10))
    repeated = recovering_owner.tick(occurred_at=NOW + timedelta(seconds=11))

    assert recovered.state is SchedulerTickState.DISPATCHED
    assert len(recovered.dispatches) == 1
    successor = recovered.dispatches[0].attempt
    assert successor.spec.ordinal == 2
    assert successor.spec.parent_attempt_id == parent.spec.attempt_id
    assert successor.spec.resume_from_run_id is None
    assert (
        successor.spec.reproduction_fingerprint == parent.spec.reproduction_fingerprint
    )
    assert repeated.state is SchedulerTickState.WAITING
    attempts = reader.list_attempts(parent.spec.fold_key)
    assert len(attempts) == 2
    assert attempts[0].projection.status is ExperimentStatus.FAILED
    assert attempts[0].projection.failure_code is ExperimentFailureCode.LEASE_LOST
    assert _live_attempt_count(database, launch.experiment_id) == 1
    database.close_all()


def test_crash_takeover_resumes_physical_checkpoint_before_experiment_index(
    tmp_path: Path,
) -> None:
    database, reader, _launch_spec = _setup(
        tmp_path,
        "experiment-crash-before-checkpoint-index",
    )
    first_owner = _coordinator(
        database,
        owner="checkpoint-crash-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(seconds=2),
    )
    first_tick = first_owner.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = first_owner.start_attempt(
        first_tick.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    parent_run_id = parent.projection.backtest_run_id
    assert parent_run_id is not None
    recovering_owner = _coordinator(
        database,
        owner="checkpoint-recovery-owner",
        clock=NOW + timedelta(seconds=10),
        resumable_checkpoints={str(parent_run_id)},
    )

    recovered = recovering_owner.tick(occurred_at=NOW + timedelta(seconds=10))

    successor = next(
        item.attempt
        for item in recovered.dispatches
        if item.attempt.spec.parent_attempt_id == parent.spec.attempt_id
    )
    attempts = reader.list_attempts(parent.spec.fold_key)
    assert attempts[0].projection.checkpoint_ref is None
    assert successor.spec.resume_from_run_id == parent_run_id
    database.close_all()


@pytest.mark.parametrize("checkpoint_resumable", [False, True])
def test_pause_resume_uses_only_an_explicitly_resumable_checkpoint_parent(
    tmp_path: Path,
    checkpoint_resumable: bool,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-pause-resume")
    checkpoints: set[str] = set()
    resumable_checkpoints = checkpoints if checkpoint_resumable else set()
    coordinator = _coordinator(
        database,
        owner="pause-owner",
        clock=NOW + timedelta(seconds=1),
        checkpoints=checkpoints,
        resumable_checkpoints=resumable_checkpoints,
        lease_duration=timedelta(minutes=5),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = coordinator.start_attempt(
        first_tick.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    parent_run_id = parent.projection.backtest_run_id
    assert parent_run_id is not None
    checkpoints.add(str(parent_run_id))
    coordinator.record_checkpoint(
        parent.spec.attempt_id,
        CheckpointRef(str(parent_run_id)),
        occurred_at=NOW + timedelta(seconds=3),
    )
    current = reader.get_experiment_projection(launch.experiment_id)
    assert current is not None
    pause = coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=current.revision,
        occurred_at=NOW + timedelta(seconds=4),
    )

    blocked = coordinator.tick(occurred_at=NOW + timedelta(seconds=5))

    assert pause.status == ExperimentStatus.PAUSE_REQUESTED.value
    assert blocked.state is SchedulerTickState.WAITING
    assert blocked.dispatches == ()
    assert len(reader.list_attempts(parent.spec.fold_key)) == 1
    coordinator.cooperative_stop_attempt(
        parent.spec.attempt_id,
        ResearchExecutionDirective.PAUSE,
        occurred_at=NOW + timedelta(seconds=6),
    )
    paused = reader.get_experiment_projection(launch.experiment_id)
    assert paused is not None
    assert paused.record.status is ExperimentStatus.PAUSED
    resume = coordinator.resume(
        experiment_id=str(launch.experiment_id),
        expected_revision=paused.revision,
        occurred_at=NOW + timedelta(seconds=7),
    )
    resumed_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=8))

    assert resume.status == ExperimentStatus.QUEUED.value
    assert resumed_tick.state is SchedulerTickState.DISPATCHED
    assert len(resumed_tick.dispatches) == 1
    successor = resumed_tick.dispatches[0].attempt
    assert successor.spec.ordinal == 2
    assert successor.spec.parent_attempt_id == parent.spec.attempt_id
    assert successor.spec.resume_from_run_id == (
        parent_run_id if checkpoint_resumable else None
    )
    assert (
        successor.spec.reproduction_fingerprint == parent.spec.reproduction_fingerprint
    )
    attempts = reader.list_attempts(parent.spec.fold_key)
    assert len(attempts) == 2
    assert attempts[0].projection.status is ExperimentStatus.CANCELLED
    assert attempts[0].projection.checkpoint_ref == CheckpointRef(str(parent_run_id))
    assert _live_attempt_count(database, launch.experiment_id) == 1
    database.close_all()


def test_consecutive_pause_resume_inherits_nearest_resumable_ancestor(
    tmp_path: Path,
) -> None:
    """A child paused before checkpointing must not discard its ancestor boundary."""
    database, reader, launch = _setup(tmp_path, "experiment-consecutive-pause")
    checkpoints: set[str] = set()
    coordinator = _coordinator(
        database,
        owner="consecutive-pause-owner",
        clock=NOW + timedelta(seconds=1),
        checkpoints=checkpoints,
        resumable_checkpoints=checkpoints,
        lease_duration=timedelta(minutes=5),
    )
    first_dispatch = coordinator.tick(
        occurred_at=NOW + timedelta(seconds=1)
    ).dispatches[0]
    first = coordinator.start_attempt(
        first_dispatch,
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    first_run_id = first.projection.backtest_run_id
    assert first_run_id is not None
    checkpoints.add(str(first_run_id))
    coordinator.record_checkpoint(
        first.spec.attempt_id,
        CheckpointRef(str(first_run_id)),
        occurred_at=NOW + timedelta(seconds=3),
    )

    first_projection = reader.get_experiment_projection(launch.experiment_id)
    assert first_projection is not None
    coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=first_projection.revision,
        occurred_at=NOW + timedelta(seconds=4),
    )
    coordinator.cooperative_stop_attempt(
        first.spec.attempt_id,
        ResearchExecutionDirective.PAUSE,
        occurred_at=NOW + timedelta(seconds=5),
    )
    paused = reader.get_experiment_projection(launch.experiment_id)
    assert paused is not None
    coordinator.resume(
        experiment_id=str(launch.experiment_id),
        expected_revision=paused.revision,
        occurred_at=NOW + timedelta(seconds=6),
    )
    second_dispatch = coordinator.tick(
        occurred_at=NOW + timedelta(seconds=7)
    ).dispatches[0]
    assert second_dispatch.attempt.spec.resume_from_run_id == first_run_id
    second = coordinator.start_attempt(
        second_dispatch,
        occurred_at=NOW + timedelta(seconds=8),
    ).attempt
    second_run_id = second.projection.backtest_run_id
    assert second_run_id is not None
    assert str(second_run_id) not in checkpoints

    running = reader.get_experiment_projection(launch.experiment_id)
    assert running is not None
    coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=running.revision,
        occurred_at=NOW + timedelta(seconds=9),
    )
    coordinator.cooperative_stop_attempt(
        second.spec.attempt_id,
        ResearchExecutionDirective.PAUSE,
        occurred_at=NOW + timedelta(seconds=10),
    )
    paused_again = reader.get_experiment_projection(launch.experiment_id)
    assert paused_again is not None
    coordinator.resume(
        experiment_id=str(launch.experiment_id),
        expected_revision=paused_again.revision,
        occurred_at=NOW + timedelta(seconds=11),
    )

    third_dispatch = coordinator.tick(
        occurred_at=NOW + timedelta(seconds=12)
    ).dispatches[0]

    third = third_dispatch.attempt
    assert third.spec.ordinal == 3
    assert third.spec.parent_attempt_id == second.spec.attempt_id
    assert third.spec.resume_from_run_id == first_run_id
    database.close_all()


def test_pause_drains_a_queued_claim_without_waiting_for_a_worker(
    tmp_path: Path,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-pause-queued")
    coordinator = _coordinator(
        database,
        owner="pause-queued-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(minutes=5),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = first_tick.dispatches[0].attempt
    current = reader.get_experiment_projection(launch.experiment_id)
    assert current is not None
    coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=current.revision,
        occurred_at=NOW + timedelta(seconds=2),
    )

    drained = coordinator.tick(occurred_at=NOW + timedelta(seconds=3))

    assert drained.state is SchedulerTickState.WAITING
    paused = reader.get_experiment_projection(launch.experiment_id)
    assert paused is not None
    assert paused.record.status is ExperimentStatus.PAUSED
    attempts = reader.list_attempts(parent.spec.fold_key)
    assert len(attempts) == 1
    assert attempts[0].projection.status is ExperimentStatus.CANCELLED
    assert _live_attempt_count(database, launch.experiment_id) == 0
    coordinator.resume(
        experiment_id=str(launch.experiment_id),
        expected_revision=paused.revision,
        occurred_at=NOW + timedelta(seconds=4),
    )
    resumed = coordinator.tick(occurred_at=NOW + timedelta(seconds=5))
    assert resumed.state is SchedulerTickState.DISPATCHED
    assert resumed.dispatches[0].attempt.spec.parent_attempt_id == (
        parent.spec.attempt_id
    )
    assert resumed.dispatches[0].attempt.spec.resume_from_run_id is None
    database.close_all()


def test_cancelled_experiment_never_recovers_or_creates_a_successor(
    tmp_path: Path,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-cancel-terminal")
    coordinator = _coordinator(
        database,
        owner="cancel-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(seconds=2),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = coordinator.start_attempt(
        first_tick.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    current = reader.get_experiment_projection(launch.experiment_id)
    assert current is not None
    cancel = coordinator.cancel(
        experiment_id=str(launch.experiment_id),
        expected_revision=current.revision,
        occurred_at=NOW + timedelta(seconds=3),
    )

    blocked = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))
    coordinator.cooperative_stop_attempt(
        parent.spec.attempt_id,
        ResearchExecutionDirective.CANCEL,
        occurred_at=NOW + timedelta(seconds=5),
    )
    after_expiry = _coordinator(
        database,
        owner="post-cancel-owner",
        clock=NOW + timedelta(seconds=10),
    ).tick(occurred_at=NOW + timedelta(seconds=10))

    assert cancel.status == ExperimentStatus.CANCEL_REQUESTED.value
    assert blocked.state is SchedulerTickState.WAITING
    assert blocked.dispatches == ()
    terminal = reader.get_experiment_projection(launch.experiment_id)
    assert terminal is not None
    assert terminal.record.status is ExperimentStatus.CANCELLED
    attempts = reader.list_attempts(parent.spec.fold_key)
    assert len(attempts) == 1
    assert attempts[0].projection.status is ExperimentStatus.CANCELLED
    assert after_expiry.state is SchedulerTickState.IDLE
    assert _live_attempt_count(database, launch.experiment_id) == 0
    assert any(
        event.subject_type.value == "fold"
        and event.status is ExperimentStatus.CANCELLED
        and event.reason_code == "cancel_fold_drained"
        for event in reader.list_status_events(launch.experiment_id)
    )
    database.close_all()


def test_terminal_tick_releases_slot_and_dispatches_next_queued_experiment(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    terminal = _launch("experiment-release-a")
    successor = _launch("experiment-release-b")
    _persist_enqueued(writer, terminal)
    _persist_enqueued(writer, successor)
    coordinator = ExperimentExecutionCoordinator(
        store=ExperimentSchedulerStore(reader, writer),
        first_attempt_factory=_RecoveryFactory(),
        owner_token="release-owner",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    assert first_tick.experiment_id == terminal.experiment_id
    current = reader.get_experiment_projection(terminal.experiment_id)
    assert current is not None
    coordinator.cancel(
        experiment_id=str(terminal.experiment_id),
        expected_revision=current.revision,
        occurred_at=NOW + timedelta(seconds=2),
    )
    drained = coordinator.tick(occurred_at=NOW + timedelta(seconds=3))
    assert drained.experiment_id == terminal.experiment_id
    cancelled = reader.get_experiment_projection(terminal.experiment_id)
    assert cancelled is not None
    assert cancelled.record.status is ExperimentStatus.CANCELLED

    handoff = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))

    assert handoff.state is SchedulerTickState.DISPATCHED
    assert handoff.experiment_id == successor.experiment_id
    assert reader.get_scheduler_slot().experiment_id == successor.experiment_id
    database.close_all()


@pytest.mark.parametrize(
    ("directive", "settled_status"),
    [
        (ResearchExecutionDirective.PAUSE, ExperimentStatus.PAUSED),
        (ResearchExecutionDirective.CANCEL, ExperimentStatus.CANCELLED),
    ],
)
def test_terminal_control_redelivery_keeps_checkpoint_and_authority_idempotent(
    tmp_path: Path,
    directive: ResearchExecutionDirective,
    settled_status: ExperimentStatus,
) -> None:
    database, reader, launch = _setup(
        tmp_path,
        f"experiment-redelivery-{directive.value}",
    )
    checkpoints: set[str] = set()
    coordinator = _coordinator(
        database,
        owner=f"redelivery-{directive.value}-owner",
        clock=NOW + timedelta(seconds=1),
        checkpoints=checkpoints,
        lease_duration=timedelta(minutes=5),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = coordinator.start_attempt(
        first_tick.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    run_id = parent.projection.backtest_run_id
    assert run_id is not None
    checkpoint_ref = CheckpointRef(str(run_id))
    checkpoints.add(str(run_id))
    coordinator.record_checkpoint(
        parent.spec.attempt_id,
        checkpoint_ref,
        occurred_at=NOW + timedelta(seconds=3),
    )
    current = reader.get_experiment_projection(launch.experiment_id)
    assert current is not None
    if directive is ResearchExecutionDirective.PAUSE:
        coordinator.pause(
            experiment_id=str(launch.experiment_id),
            expected_revision=current.revision,
            occurred_at=NOW + timedelta(seconds=4),
        )
    else:
        coordinator.cancel(
            experiment_id=str(launch.experiment_id),
            expected_revision=current.revision,
            occurred_at=NOW + timedelta(seconds=4),
        )
    coordinator.cooperative_stop_attempt(
        parent.spec.attempt_id,
        directive,
        occurred_at=NOW + timedelta(seconds=5),
    )
    settled_events = reader.list_status_events(launch.experiment_id)

    replayed_checkpoint = coordinator.record_checkpoint(
        parent.spec.attempt_id,
        checkpoint_ref,
        occurred_at=NOW + timedelta(seconds=6),
    )
    replayed = coordinator.cooperative_stop_attempt(
        parent.spec.attempt_id,
        directive,
        occurred_at=NOW + timedelta(seconds=7),
    )

    assert replayed_checkpoint.projection.status is ExperimentStatus.CANCELLED
    assert replayed.projection.record.status is settled_status
    assert reader.list_status_events(launch.experiment_id) == settled_events
    assert (
        coordinator.poll_execution_directive(
            parent.spec.attempt_id,
            occurred_at=NOW + timedelta(seconds=8),
        )
        is directive
    )
    if directive is ResearchExecutionDirective.PAUSE:
        assert reader.get_scheduler_slot().experiment_id == launch.experiment_id
        assert coordinator.renew_lease().experiment_id == launch.experiment_id
    database.close_all()


def test_explicit_system_retry_requeues_before_creating_one_successor(
    tmp_path: Path,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-explicit-retry")
    coordinator = _coordinator(
        database,
        owner="retry-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(minutes=5),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = coordinator.start_attempt(
        first_tick.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    coordinator.fail_attempt(
        parent.spec.attempt_id,
        ExperimentFailureCode.SYSTEM_ERROR,
        occurred_at=NOW + timedelta(seconds=3),
    )
    failed_fold = next(
        item
        for item in reader.list_folds(launch.experiment_id)
        if item.spec.key == parent.spec.fold_key
    )

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.retry_fold(
            experiment_id=str(launch.experiment_id),
            candidate_id=str(parent.spec.fold_key.candidate_id),
            fold_id=str(parent.spec.fold_key.fold_id),
            expected_revision=failed_fold.projection.revision - 1,
            occurred_at=NOW + timedelta(seconds=4),
        )
    assert exc_info.value.details["reason"] == "stale_fold_revision"
    renewed = coordinator.renew_lease()
    assert renewed.experiment_id == launch.experiment_id

    retry_identity = build_mutation_idempotency(
        operation_id="research_retry_fold_experiment",
        resource_id=canonical_resource_id(
            "experiment_fold",
            {
                "experiment_id": str(launch.experiment_id),
                "candidate_id": str(parent.spec.fold_key.candidate_id),
                "fold_id": str(parent.spec.fold_key.fold_id),
            },
        ),
        raw_key="retry-integration-001",
        request_payload={
            "candidate_id": str(parent.spec.fold_key.candidate_id),
            "fold_id": str(parent.spec.fold_key.fold_id),
            "expected_revision": failed_fold.projection.revision,
        },
    )
    first_retry = coordinator.retry_fold(
        experiment_id=str(launch.experiment_id),
        candidate_id=str(parent.spec.fold_key.candidate_id),
        fold_id=str(parent.spec.fold_key.fold_id),
        expected_revision=failed_fold.projection.revision,
        occurred_at=NOW + timedelta(seconds=5),
        idempotency=retry_identity,
    )
    event_count = len(reader.list_status_events(launch.experiment_id))
    replay_retry = _coordinator(
        database,
        owner="retry-restarted-owner",
        clock=NOW + timedelta(seconds=5),
        lease_duration=timedelta(minutes=5),
    ).retry_fold(
        experiment_id=str(launch.experiment_id),
        candidate_id=str(parent.spec.fold_key.candidate_id),
        fold_id=str(parent.spec.fold_key.fold_id),
        expected_revision=failed_fold.projection.revision,
        occurred_at=NOW + timedelta(seconds=5),
        idempotency=retry_identity,
    )

    assert replay_retry == first_retry
    assert replay_retry.replayed is True
    assert len(reader.list_status_events(launch.experiment_id)) == event_count
    assert len(reader.list_attempts(parent.spec.fold_key)) == 1
    retried = coordinator.tick(occurred_at=NOW + timedelta(seconds=6))
    assert retried.state is SchedulerTickState.DISPATCHED
    assert len(retried.dispatches) == 1
    successor = retried.dispatches[0].attempt
    assert successor.spec.ordinal == 2
    assert successor.spec.parent_attempt_id == parent.spec.attempt_id
    assert successor.spec.resume_from_run_id is None
    assert successor.spec.reproduction_fingerprint == (
        parent.spec.reproduction_fingerprint
    )
    assert _live_attempt_count(database, launch.experiment_id) == 1
    database.close_all()


def test_idempotent_retry_returns_persisted_receipt_across_post_write_projection_race(
    tmp_path: Path,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-retry-readback-race")
    post_write_barrier = Barrier(2)
    racing_store = _PostWriteRetryStore(_store(database), post_write_barrier)
    coordinator = _coordinator(
        database,
        owner="retry-race-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(minutes=5),
        scheduler_store=cast("ExperimentSchedulerStoreProtocol", racing_store),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = coordinator.start_attempt(
        first_tick.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    coordinator.fail_attempt(
        parent.spec.attempt_id,
        ExperimentFailureCode.SYSTEM_ERROR,
        occurred_at=NOW + timedelta(seconds=3),
    )
    failed_fold = next(
        item
        for item in reader.list_folds(launch.experiment_id)
        if item.spec.key == parent.spec.fold_key
    )
    identity = build_mutation_idempotency(
        operation_id="research_retry_fold_experiment",
        resource_id=canonical_resource_id(
            "experiment_fold",
            {
                "experiment_id": str(launch.experiment_id),
                "candidate_id": str(parent.spec.fold_key.candidate_id),
                "fold_id": str(parent.spec.fold_key.fold_id),
            },
        ),
        raw_key="retry-readback-race-001",
        request_payload={
            "candidate_id": str(parent.spec.fold_key.candidate_id),
            "fold_id": str(parent.spec.fold_key.fold_id),
            "expected_revision": failed_fold.projection.revision,
        },
    )
    request = {
        "experiment_id": str(launch.experiment_id),
        "candidate_id": str(parent.spec.fold_key.candidate_id),
        "fold_id": str(parent.spec.fold_key.fold_id),
        "expected_revision": failed_fold.projection.revision,
        "occurred_at": NOW + timedelta(seconds=5),
        "idempotency": identity,
    }

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(coordinator.retry_fold, **request)
        post_write_barrier.wait(timeout=5)
        concurrent_store = _store(database)
        current = concurrent_store.load_snapshot(launch.experiment_id).projection
        concurrent_store.transition_operator_experiment(
            current,
            target_status=ExperimentStatus.PAUSE_REQUESTED,
            target_desired_state=ExperimentDesiredState.PAUSE,
            expected_revision=current.revision,
            occurred_at=NOW + timedelta(seconds=6),
            reason_code="operator_pause",
            detail={},
        )
        post_write_barrier.wait(timeout=5)
        first = future.result(timeout=5)

    replay = _coordinator(
        database,
        owner="retry-race-replay-owner",
        clock=NOW + timedelta(seconds=7),
    ).retry_fold(**request)

    assert first == replay
    assert first.replayed is False
    assert replay.replayed is True
    database.close_all()


def test_pause_wins_queued_dispatch_start_race_without_poisoning_authority(
    tmp_path: Path,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-pause-start-race")
    coordinator = _coordinator(
        database,
        owner="pause-race-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(minutes=5),
    )
    first_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    dispatch = first_tick.dispatches[0]
    current = reader.get_experiment_projection(launch.experiment_id)
    assert current is not None
    coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=current.revision,
        occurred_at=NOW + timedelta(seconds=2),
    )

    with pytest.raises(ExperimentExecutionControlChanged):
        coordinator.start_attempt(
            dispatch,
            occurred_at=NOW + timedelta(seconds=3),
        )

    renewed = coordinator.renew_lease()
    assert renewed.experiment_id == launch.experiment_id
    assert renewed.revision > first_tick.dispatches[0].fold.projection.revision
    database.close_all()


def test_two_recovery_coordinators_cannot_create_two_live_successors(
    tmp_path: Path,
) -> None:
    database, reader, launch = _setup(tmp_path, "experiment-concurrent-recovery")
    first_owner = _coordinator(
        database,
        owner="crashed-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(seconds=2),
    )
    first_tick = first_owner.tick(occurred_at=NOW + timedelta(seconds=1))
    parent = first_owner.start_attempt(
        first_tick.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    barrier = Barrier(2)
    contenders = (
        _coordinator(
            database, owner="recovery-owner-b", clock=NOW + timedelta(seconds=10)
        ),
        _coordinator(
            database, owner="recovery-owner-c", clock=NOW + timedelta(seconds=10)
        ),
    )

    def race(coordinator: ExperimentExecutionCoordinator) -> SchedulerTickState:
        barrier.wait()
        return coordinator.tick(occurred_at=NOW + timedelta(seconds=10)).state

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = tuple(pool.map(race, contenders))

    assert states.count(SchedulerTickState.DISPATCHED) == 1
    assert states.count(SchedulerTickState.LEASE_BUSY) == 1
    attempts = reader.list_attempts(parent.spec.fold_key)
    assert len(attempts) == 2
    assert attempts[0].projection.status is ExperimentStatus.FAILED
    assert attempts[0].projection.failure_code is ExperimentFailureCode.LEASE_LOST
    assert attempts[1].spec.ordinal == 2
    assert attempts[1].spec.parent_attempt_id == parent.spec.attempt_id
    assert _live_attempt_count(database, launch.experiment_id) == 1
    database.close_all()
