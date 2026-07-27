"""Pure durable-scheduler orchestration tests for first-attempt execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Event, Lock

import pytest
from ditto_analysis.errors import ExperimentIntegrityError, ExperimentLeaseLostError
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
    ExperimentProjection,
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
    LeaseFence,
    LogicalTrialIdentity,
    ResearchMetricDirection,
    ResearchMetricId,
    SchedulerLease,
    SchedulerSlot,
    SnapshotId,
    StrategyVersion,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    PersistedAttemptStart,
    SchedulerTickState,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
    FirstAttempt,
    QueuedAttempt,
)

NOW = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)


def _launch(
    *,
    worker_count: int = 2,
    candidate_count: int = 3,
    failure_policy: ExperimentFailurePolicy = (
        ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES
    ),
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
        experiment_id=ExperimentId("experiment-1"),
        strategy_version=StrategyVersion("strategy@1"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-1"),
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
            "Test coordinator behavior.",
            TrialFamilyDeclaration(
                "coordinator-test-family",
                tuple(
                    LogicalTrialIdentity(
                        ExperimentId("experiment-1"),
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
        worker_count=worker_count,
        failure_policy=failure_policy,
        budget=ExperimentBudget(128, 512),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _fold(
    candidate_ordinal: int,
    fold_ordinal: int,
    role: FoldRole,
) -> FoldView:
    key = FoldKey(
        ExperimentId("experiment-1"),
        CandidateId(f"candidate-{candidate_ordinal}"),
        FoldId(f"fold-{candidate_ordinal}-{fold_ordinal}"),
    )
    train = (
        None
        if role is FoldRole.EXPLORATION
        else DateWindow(date(2020, 1, 1), date(2024, 12, 31))
    )
    spec = FoldPersistenceSpec.create(
        key,
        fold_ordinal,
        role,
        train,
        DateWindow(date(2025, fold_ordinal, 1), date(2025, fold_ordinal, 28)),
        2,
        1,
    )
    return FoldView(
        spec,
        FoldProjection(key, ExperimentStatus.QUEUED, None, NOW, NOW, 0),
    )


class _FirstAttemptFactory:
    def __init__(self) -> None:
        self.calls: list[FoldKey] = []

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        self.calls.append(fold.spec.key)
        attempt_id = AttemptId(
            "attempt-"
            + str(fold.spec.key.candidate_id)
            + "-"
            + str(fold.spec.key.fold_id)
        )
        spec = AttemptPersistenceSpec(
            attempt_id=attempt_id,
            fold_key=fold.spec.key,
            ordinal=1,
            parent_attempt_id=None,
            resume_from_run_id=None,
            reproduction_fingerprint=ContentHash("c" * 64),
            created_at=occurred_at,
        )
        return FirstAttempt(
            spec=spec,
            projection=AttemptProjection(
                attempt_id,
                ExperimentStatus.QUEUED,
                None,
                None,
                None,
                occurred_at,
                occurred_at,
                0,
            ),
        )

    def create_successor(
        self,
        fold: FoldView,
        parent: AttemptView,
        *,
        resume_from_run_id: BacktestRunId | None,
        occurred_at: datetime,
    ) -> QueuedAttempt:
        self.calls.append(fold.spec.key)
        ordinal = parent.spec.ordinal + 1
        attempt_id = AttemptId(f"{parent.spec.attempt_id}-retry-{ordinal}")
        spec = AttemptPersistenceSpec(
            attempt_id=attempt_id,
            fold_key=fold.spec.key,
            ordinal=ordinal,
            parent_attempt_id=parent.spec.attempt_id,
            resume_from_run_id=resume_from_run_id,
            reproduction_fingerprint=parent.spec.reproduction_fingerprint,
            created_at=occurred_at,
        )
        return QueuedAttempt(
            spec,
            AttemptProjection(
                attempt_id,
                ExperimentStatus.QUEUED,
                None,
                None,
                None,
                occurred_at,
                occurred_at,
                0,
            ),
        )


class _DerivedAttemptPersistenceSpec(AttemptPersistenceSpec):
    """Adversarial subtype that must not cross the exact attempt boundary."""


class _SchedulerStore:
    def __init__(
        self,
        *,
        worker_count: int = 2,
        candidate_count: int = 3,
        failure_policy: ExperimentFailurePolicy = (
            ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES
        ),
    ) -> None:
        self.launch = _launch(
            worker_count=worker_count,
            candidate_count=candidate_count,
            failure_policy=failure_policy,
        )
        self.projection = ExperimentProjection(
            ExperimentRecord(
                self.launch.experiment_id,
                ExperimentStatus.QUEUED,
                ExperimentDesiredState.RUN,
                ExperimentStage.PREFLIGHT,
                NOW,
            ),
            1,
            1,
            NOW,
        )
        self.folds = [
            fold
            for candidate in range(1, candidate_count + 1)
            for fold in (
                _fold(candidate, 1, FoldRole.EXPLORATION),
                _fold(candidate, 2, FoldRole.WALK_FORWARD),
                _fold(candidate, 3, FoldRole.WALK_FORWARD),
                _fold(candidate, 4, FoldRole.HOLDOUT),
            )
        ]
        self.attempts: dict[AttemptId, AttemptView] = {}
        self.slot = SchedulerSlot("global", None, None, None, None, None, 0)
        self.claimed_keys: list[FoldKey] = []
        self.write_fences: list[int] = []
        self.raise_lease_lost_on_claim = False
        self.raise_integrity_failure_on_claim = False
        self.raise_lease_lost_on_fold_transition = False
        self.raise_integrity_on_slot_read = False
        self.claim_barrier: Barrier | None = None
        self.block_first_transition = False
        self.first_transition_entered = Event()
        self.release_first_transition = Event()
        self.controlled_transitions: list[dict[str, object]] = []
        self._transition_count = 0
        self._active_writes = 0
        self.max_active_writes = 0
        self._active_lock = Lock()
        self._lease_lock = Lock()

    def list_dispatchable_experiments(self) -> tuple[ExperimentProjection, ...]:
        if self.slot.experiment_id is not None:
            return ()
        if self.projection.record.status is ExperimentStatus.QUEUED:
            return (self.projection,)
        return ()

    def get_scheduler_slot(self) -> SchedulerSlot:
        if self.raise_integrity_on_slot_read:
            raise ExperimentIntegrityError(
                "slot corrupt",
                details={"reason_code": "scheduler_slot_missing"},
            )
        return self.slot

    def try_claim_lease(
        self,
        experiment_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
        lease_until_epoch_us: int,
    ) -> SchedulerLease | None:
        if self.claim_barrier is not None:
            self.claim_barrier.wait(timeout=5)
        with self._lease_lock:
            if self.slot.revision != expected_revision:
                raise ExperimentLeaseLostError(
                    "stale",
                    details={"reason_code": "scheduler_lease_stale_revision"},
                )
            if (
                self.slot.owner_token is not None
                and self.slot.lease_until_epoch_us is not None
                and self.slot.lease_until_epoch_us > now_epoch_us
            ):
                return None
            lease = SchedulerLease(
                experiment_id,
                owner_token,
                lease_until_epoch_us,
                now_epoch_us,
                now_epoch_us,
                expected_revision + 1,
            )
            self.slot = SchedulerSlot(
                "global",
                experiment_id,
                owner_token,
                lease_until_epoch_us,
                now_epoch_us,
                now_epoch_us,
                lease.revision,
            )
            return lease

    def renew_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        new_lease_until_epoch_us: int,
    ) -> SchedulerLease:
        renewed = SchedulerLease(
            lease.experiment_id,
            lease.owner_token,
            new_lease_until_epoch_us,
            lease.acquired_at_epoch_us,
            now_epoch_us,
            lease.revision + 1,
        )
        self.slot = replace(
            self.slot,
            lease_until_epoch_us=new_lease_until_epoch_us,
            renewed_at_epoch_us=now_epoch_us,
            revision=renewed.revision,
        )
        return renewed

    def load_snapshot(self, experiment_id: ExperimentId) -> ExperimentSchedulerSnapshot:
        assert experiment_id == self.launch.experiment_id
        return ExperimentSchedulerSnapshot(
            projection=self.projection,
            launch_spec=self.launch,
            folds=tuple(self.folds),
            attempts=tuple(self.attempts.values()),
        )

    def transition_to_running(
        self,
        projection: ExperimentProjection,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> ExperimentProjection:
        self.write_fences.append(lease.revision)
        self.projection = replace(
            projection,
            record=replace(
                projection.record,
                status=ExperimentStatus.RUNNING,
                stage=ExperimentStage.EXPLORATION,
            ),
            revision=projection.revision + 1,
            updated_at=occurred_at,
        )
        return self.projection

    def advance_stage(
        self,
        projection: ExperimentProjection,
        target_stage: ExperimentStage,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> ExperimentProjection:
        self.write_fences.append(lease.revision)
        self.projection = replace(
            projection,
            record=replace(projection.record, stage=target_stage),
            revision=projection.revision + 1,
            updated_at=occurred_at,
        )
        return self.projection

    def claim_first_attempt(
        self,
        fold: FoldView,
        first_attempt: FirstAttempt,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]:
        return self.claim_attempt(
            fold,
            first_attempt,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )

    def claim_attempt(
        self,
        fold: FoldView,
        queued_attempt: QueuedAttempt,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]:
        if self.raise_integrity_failure_on_claim:
            raise ExperimentIntegrityError(
                "corrupt",
                details={"reason_code": "projection_integrity_failed"},
            )
        if self.raise_lease_lost_on_claim:
            raise ExperimentLeaseLostError(
                "lost",
                details={"reason_code": "scheduler_lease_lost"},
            )
        self.write_fences.append(lease.revision)
        index = self.folds.index(fold)
        claimed = replace(
            fold,
            projection=replace(
                fold.projection,
                status=ExperimentStatus.RUNNING,
                claim_owner_token=lease.owner_token,
                updated_at=occurred_at,
                revision=fold.projection.revision + 1,
            ),
        )
        self.folds[index] = claimed
        attempt = AttemptView(queued_attempt.spec, queued_attempt.projection)
        self.attempts[queued_attempt.spec.attempt_id] = attempt
        self.claimed_keys.append(fold.spec.key)
        return claimed, attempt

    def recover_interrupted_fold(
        self,
        fold: FoldView,
        attempt: AttemptView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]:
        self.write_fences.append(lease.revision)
        recovered_attempt = replace(
            attempt,
            projection=replace(
                attempt.projection,
                status=ExperimentStatus.FAILED,
                failure_code=ExperimentFailureCode.LEASE_LOST,
                updated_at=occurred_at,
                revision=attempt.projection.revision + 1,
            ),
        )
        self.attempts[attempt.spec.attempt_id] = recovered_attempt
        fold_index = self.folds.index(fold)
        recovered_fold = replace(
            fold,
            projection=replace(
                fold.projection,
                status=ExperimentStatus.QUEUED,
                claim_owner_token=None,
                updated_at=occurred_at,
                revision=fold.projection.revision + 1,
            ),
        )
        self.folds[fold_index] = recovered_fold
        return recovered_fold, recovered_attempt

    def transition_attempt(
        self,
        attempt: AttemptView,
        *,
        target_status: ExperimentStatus,
        backtest_run_id: BacktestRunId | None,
        failure_code: ExperimentFailureCode | None,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> AttemptView:
        self._enter_write()
        try:
            self._transition_count += 1
            if self.block_first_transition and self._transition_count == 1:
                self.first_transition_entered.set()
                assert self.release_first_transition.wait(timeout=5)
            self.write_fences.append(lease.revision)
            updated = replace(
                attempt,
                projection=replace(
                    attempt.projection,
                    status=target_status,
                    backtest_run_id=backtest_run_id,
                    failure_code=failure_code,
                    updated_at=occurred_at,
                    revision=attempt.projection.revision + 1,
                ),
            )
            self.attempts[attempt.spec.attempt_id] = updated
            return updated
        finally:
            self._leave_write()

    def transition_fold(
        self,
        fold: FoldView,
        *,
        target_status: ExperimentStatus,
        failure_code: ExperimentFailureCode | None,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> FoldView:
        if self.raise_lease_lost_on_fold_transition:
            raise ExperimentLeaseLostError(
                "lost",
                details={"reason_code": "scheduler_lease_lost"},
            )
        self.write_fences.append(lease.revision)
        index = self.folds.index(fold)
        updated = replace(
            fold,
            projection=replace(
                fold.projection,
                status=target_status,
                claim_owner_token=None,
                updated_at=occurred_at,
                revision=fold.projection.revision + 1,
            ),
        )
        self.folds[index] = updated
        return updated

    def transition_controlled_experiment(
        self,
        projection: ExperimentProjection,
        *,
        target_status: ExperimentStatus,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
        attempt_started: bool,
        reason_code: str,
    ) -> ExperimentProjection:
        """Test double for the lease-fenced whole-experiment transition."""
        self.write_fences.append(lease.revision)
        self.controlled_transitions.append(
            {
                "target_status": target_status,
                "target_stage": projection.record.stage,
                "reason_code": reason_code,
                "attempt_started": attempt_started,
            }
        )
        self.projection = replace(
            projection,
            record=replace(
                projection.record,
                status=target_status,
            ),
            revision=projection.revision + 1,
            updated_at=occurred_at,
        )
        return self.projection

    def _enter_write(self) -> None:
        with self._active_lock:
            self._active_writes += 1
            self.max_active_writes = max(self.max_active_writes, self._active_writes)

    def _leave_write(self) -> None:
        with self._active_lock:
            self._active_writes -= 1

    def release_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
    ) -> SchedulerSlot:
        """Release the singleton slot back to free state (test double)."""
        self.slot = SchedulerSlot(
            self.slot.slot_id,
            None,
            None,
            None,
            self.slot.acquired_at_epoch_us,
            self.slot.renewed_at_epoch_us,
            self.slot.revision + 1,
        )
        return self.slot


def _coordinator(
    store: _SchedulerStore,
    *,
    owner_token: str | None = None,
    clock_now: datetime = NOW,
    evidence_collector: _FakeEvidenceCollector | None = None,
) -> tuple[ExperimentExecutionCoordinator, _FirstAttemptFactory]:
    factory = _FirstAttemptFactory()
    return (
        ExperimentExecutionCoordinator(
            store=store,
            first_attempt_factory=factory,
            owner_token=owner_token or "coordinator-a",
            lease_duration=timedelta(minutes=5),
            clock=lambda: clock_now,
            evidence_collector=evidence_collector,
        ),
        factory,
    )


class _FakeEvidenceCollector:
    """Test double for ExperimentEvidenceCollector (duck-typed, basic mode)."""

    def __init__(self, *, raise_error: Exception | None = None) -> None:
        self.collect_calls: list[dict[str, object]] = []
        self.raise_error = raise_error

    def collect(
        self,
        experiment_id: ExperimentId,
        *,
        lease_fence: object,
        now_epoch_us: int,
        created_at: datetime,
    ) -> object:
        self.collect_calls.append(
            {
                "experiment_id": experiment_id,
                "lease_fence": lease_fence,
                "now_epoch_us": now_epoch_us,
                "created_at": created_at,
            }
        )
        if self.raise_error is not None:
            raise self.raise_error
        return None


class _MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _start_all_dispatched(
    coordinator: ExperimentExecutionCoordinator,
    result,
) -> None:
    for ordinal, dispatch in enumerate(result.dispatches, start=1):
        coordinator.start_attempt(
            dispatch,
            occurred_at=NOW + timedelta(seconds=ordinal),
        )


def _set_running_stage(
    store: _SchedulerStore,
    stage: ExperimentStage,
) -> None:
    store.projection = replace(
        store.projection,
        record=replace(
            store.projection.record,
            status=ExperimentStatus.RUNNING,
            stage=stage,
        ),
    )
    store.slot = SchedulerSlot(
        "global",
        store.launch.experiment_id,
        "expired-owner",
        NOW_US - 1,
        NOW_US - 10,
        NOW_US - 10,
        1,
    )


def _persist_attempt(
    store: _SchedulerStore,
    *,
    candidate_ordinal: int,
    status: ExperimentStatus,
    owner_token: str | None,
    failure_code: ExperimentFailureCode | None = None,
) -> None:
    fold_index = next(
        index
        for index, fold in enumerate(store.folds)
        if fold.spec.key.candidate_id == CandidateId(f"candidate-{candidate_ordinal}")
        and fold.spec.fold_role is FoldRole.EXPLORATION
    )
    fold = store.folds[fold_index]
    persisted_fold = replace(
        fold,
        projection=replace(
            fold.projection,
            status=status,
            claim_owner_token=owner_token,
        ),
    )
    store.folds[fold_index] = persisted_fold
    first_attempt = _FirstAttemptFactory().create(fold, NOW)
    store.attempts[first_attempt.spec.attempt_id] = AttemptView(
        first_attempt.spec,
        replace(
            first_attempt.projection,
            status=status,
            backtest_run_id=(
                None
                if status is ExperimentStatus.QUEUED
                else BacktestRunId(f"run-{candidate_ordinal}")
            ),
            failure_code=failure_code,
        ),
    )


def test_tick_acquires_singleton_lease_and_dispatches_capacity_in_order() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=3)
    coordinator, factory = _coordinator(store)

    result = coordinator.tick(occurred_at=NOW)

    assert result.state is SchedulerTickState.DISPATCHED
    candidate_ids = [
        dispatch.fold.spec.key.candidate_id.value for dispatch in result.dispatches
    ]
    assert candidate_ids == [
        "candidate-1",
        "candidate-2",
    ]
    assert factory.calls == store.claimed_keys
    assert result.progress is not None
    assert result.progress.worker_limit == 2
    assert result.progress.live_attempt_count == 2


def test_second_coordinator_cannot_enter_the_singleton_slot() -> None:
    store = _SchedulerStore()
    first, _factory = _coordinator(store, owner_token="owner-a")
    second, _second_factory = _coordinator(store, owner_token="owner-b")
    first.tick(occurred_at=NOW)

    result = second.tick(occurred_at=NOW + timedelta(seconds=1))

    assert result.state is SchedulerTickState.LEASE_BUSY
    assert len(store.claimed_keys) == 2


def test_concurrent_acquire_loser_is_busy_without_poisoning_its_authority() -> None:
    store = _SchedulerStore()
    store.claim_barrier = Barrier(2)
    first, _factory = _coordinator(store, owner_token="owner-a")
    second, _second_factory = _coordinator(store, owner_token="owner-b")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(first.tick, occurred_at=NOW),
            executor.submit(second.tick, occurred_at=NOW),
        )
        results = tuple(future.result(timeout=5) for future in futures)
    store.claim_barrier = None

    assert {result.state for result in results} == {
        SchedulerTickState.DISPATCHED,
        SchedulerTickState.LEASE_BUSY,
    }
    loser = first if results[0].state is SchedulerTickState.LEASE_BUSY else second
    assert loser.tick(occurred_at=NOW + timedelta(seconds=1)).state is (
        SchedulerTickState.LEASE_BUSY
    )


def test_repeated_tick_uses_durable_capacity_without_duplicate_claim() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=3)
    coordinator, _factory = _coordinator(store)
    first = coordinator.tick(occurred_at=NOW)

    second = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))

    assert first.progress is not None
    assert first.progress.live_attempt_count == 2
    assert second.state is SchedulerTickState.WAITING
    assert second.dispatches == ()
    assert len(store.claimed_keys) == 2


def test_four_worker_spec_dispatches_four_and_never_uses_an_unbounded_default() -> None:
    store = _SchedulerStore(worker_count=4, candidate_count=5)
    coordinator, _factory = _coordinator(store)

    result = coordinator.tick(occurred_at=NOW)

    assert len(result.dispatches) == 4
    assert result.progress is not None
    assert result.progress.worker_limit == 4
    assert result.progress.available_capacity == 0


def test_scheduler_rejects_three_worker_legacy_launch() -> None:
    store = _SchedulerStore(worker_count=3, candidate_count=3)
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)

    assert exc_info.value.details["reason"] == "worker_limit_must_be_two_or_four"
    assert store.claimed_keys == []
    assert store.slot.experiment_id is None


def test_invalid_audit_timestamp_is_rejected_before_lease_claim() -> None:
    store = _SchedulerStore()
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=datetime(2026, 7, 20, 1, 0))

    assert exc_info.value.details["reason"] == "occurred_at_must_be_utc"
    assert store.slot.experiment_id is None


@pytest.mark.parametrize(
    ("stage", "incomplete_role"),
    [
        (ExperimentStage.WALK_FORWARD, FoldRole.EXPLORATION),
        (ExperimentStage.CANDIDATE_SELECTION, FoldRole.WALK_FORWARD),
    ],
)
def test_persisted_stage_rejects_a_queued_prior_fold_frontier(
    stage: ExperimentStage,
    incomplete_role: FoldRole,
) -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    _set_running_stage(store, stage)
    for index, fold in enumerate(store.folds):
        if (
            fold.spec.fold_role is incomplete_role
            and fold.spec.key.candidate_id == CandidateId("candidate-1")
        ):
            continue
        if fold.spec.fold_role in {FoldRole.EXPLORATION, FoldRole.WALK_FORWARD}:
            store.folds[index] = replace(
                fold,
                projection=replace(
                    fold.projection,
                    status=ExperimentStatus.COMPLETED,
                ),
            )
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert exc_info.value.details["reason"] == "stage_frontier_incomplete"
    assert exc_info.value.details["stage"] == stage.value
    assert exc_info.value.details["fold_role"] == incomplete_role.value
    assert store.claimed_keys == []
    assert store.write_fences == []


def test_future_fold_cannot_be_skipped_without_candidate_isolation() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    _set_running_stage(store, ExperimentStage.EXPLORATION)
    future_index = next(
        index
        for index, fold in enumerate(store.folds)
        if fold.spec.fold_role is FoldRole.WALK_FORWARD
    )
    future = store.folds[future_index]
    store.folds[future_index] = replace(
        future,
        projection=replace(
            future.projection,
            status=ExperimentStatus.CANCELLED,
        ),
    )
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert exc_info.value.details["reason"] == "future_stage_fold_outcome_detected"
    assert store.claimed_keys == []
    assert store.write_fences == []


@pytest.mark.parametrize("early_return", ["fail_fast", "recovery"])
def test_durable_overcapacity_preempts_poisoned_early_return(
    early_return: str,
) -> None:
    store = _SchedulerStore(
        worker_count=2,
        candidate_count=4,
        failure_policy=ExperimentFailurePolicy.FAIL_FAST,
    )
    coordinator, _factory = _coordinator(store)
    initial = coordinator.tick(occurred_at=NOW)
    assert initial.state is SchedulerTickState.DISPATCHED
    assert store.slot.owner_token is not None
    _persist_attempt(
        store,
        candidate_ordinal=3,
        status=ExperimentStatus.RUNNING,
        owner_token=(
            "stale-owner" if early_return == "recovery" else store.slot.owner_token
        ),
    )
    if early_return == "fail_fast":
        _persist_attempt(
            store,
            candidate_ordinal=4,
            status=ExperimentStatus.FAILED,
            owner_token=None,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        )
    write_count = len(store.write_fences)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW + timedelta(seconds=1))

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "durable_worker_capacity_exceeded"
    assert exc_info.value.details["worker_limit"] == 2
    assert exc_info.value.details["live_attempt_count"] == 3
    assert len(store.claimed_keys) == 2
    assert len(store.write_fences) == write_count


def test_completed_exploration_advances_then_dispatches_only_walk_forward() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    coordinator, _factory = _coordinator(store)
    exploration = coordinator.tick(occurred_at=NOW)
    _start_all_dispatched(coordinator, exploration)
    for dispatch in exploration.dispatches:
        coordinator.complete_attempt(
            dispatch.attempt.spec.attempt_id,
            occurred_at=NOW + timedelta(seconds=10),
        )

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=11))

    assert result.state is SchedulerTickState.DISPATCHED
    assert store.projection.record.stage is ExperimentStage.WALK_FORWARD
    assert {item.fold.spec.fold_role for item in result.dispatches} == {
        FoldRole.WALK_FORWARD
    }
    assert all(
        item.fold.spec.fold_role is not FoldRole.HOLDOUT for item in result.dispatches
    )


def test_walk_forward_completion_stops_at_candidate_selection_without_holdout() -> None:
    store = _SchedulerStore(worker_count=4, candidate_count=1)
    coordinator, _factory = _coordinator(store)
    exploration = coordinator.tick(occurred_at=NOW)
    _start_all_dispatched(coordinator, exploration)
    coordinator.complete_attempt(
        exploration.dispatches[0].attempt.spec.attempt_id,
        occurred_at=NOW + timedelta(seconds=2),
    )
    walk_forward = coordinator.tick(occurred_at=NOW + timedelta(seconds=3))
    _start_all_dispatched(coordinator, walk_forward)
    for dispatch in walk_forward.dispatches:
        coordinator.complete_attempt(
            dispatch.attempt.spec.attempt_id,
            occurred_at=NOW + timedelta(seconds=4),
        )

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=5))

    assert result.state is SchedulerTickState.CANDIDATE_SELECTION
    assert result.dispatches == ()
    assert store.projection.record.stage is ExperimentStage.CANDIDATE_SELECTION
    assert all(
        fold.projection.status is ExperimentStatus.QUEUED
        for fold in store.folds
        if fold.spec.fold_role is FoldRole.HOLDOUT
    )


def test_holdout_stage_is_a_hard_dispatch_boundary_for_task9() -> None:
    store = _SchedulerStore()
    _set_running_stage(store, ExperimentStage.HOLDOUT)
    for index, fold in enumerate(store.folds):
        if fold.spec.fold_role in {FoldRole.EXPLORATION, FoldRole.WALK_FORWARD}:
            store.folds[index] = replace(
                fold,
                projection=replace(
                    fold.projection,
                    status=ExperimentStatus.COMPLETED,
                ),
            )
    coordinator, _factory = _coordinator(store)

    result = coordinator.tick(occurred_at=NOW)

    assert result.state is SchedulerTickState.HOLDOUT_GATED
    assert result.dispatches == ()
    assert store.claimed_keys == []


def test_candidate_failure_releases_capacity_for_other_candidates() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=3)
    coordinator, _factory = _coordinator(store)
    initial = coordinator.tick(occurred_at=NOW)
    _start_all_dispatched(coordinator, initial)
    failed = initial.dispatches[0]
    coordinator.fail_attempt(
        failed.attempt.spec.attempt_id,
        ExperimentFailureCode.CANDIDATE_FAILED,
        occurred_at=NOW + timedelta(seconds=3),
    )

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))

    assert result.state is SchedulerTickState.DISPATCHED
    assert [item.fold.spec.key.candidate_id.value for item in result.dispatches] == [
        "candidate-3"
    ]
    assert result.progress is not None
    assert result.progress.failed_candidate_attempt_count == 1


def test_fail_fast_policy_stops_after_the_first_candidate_failure() -> None:
    store = _SchedulerStore(
        worker_count=2,
        candidate_count=3,
        failure_policy=ExperimentFailurePolicy.FAIL_FAST,
    )
    coordinator, _factory = _coordinator(store)
    initial = coordinator.tick(occurred_at=NOW)
    _start_all_dispatched(coordinator, initial)
    coordinator.fail_attempt(
        initial.dispatches[0].attempt.spec.attempt_id,
        ExperimentFailureCode.CANDIDATE_FAILED,
        occurred_at=NOW + timedelta(seconds=3),
    )
    claim_count = len(store.claimed_keys)

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))

    assert result.state is SchedulerTickState.FAIL_FAST
    assert result.dispatches == ()
    assert len(store.claimed_keys) == claim_count


def test_all_candidate_failures_never_advance_to_candidate_selection() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    coordinator, _factory = _coordinator(store)
    initial = coordinator.tick(occurred_at=NOW)
    _start_all_dispatched(coordinator, initial)
    for dispatch in initial.dispatches:
        coordinator.fail_attempt(
            dispatch.attempt.spec.attempt_id,
            ExperimentFailureCode.CANDIDATE_FAILED,
            occurred_at=NOW + timedelta(seconds=3),
        )

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))

    assert result.state is SchedulerTickState.FAIL_FAST
    assert result.dispatches == ()
    assert store.projection.record.stage is ExperimentStage.EXPLORATION


def test_live_holdout_work_during_exploration_fails_integrity_closed() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    store.projection = replace(
        store.projection,
        record=replace(
            store.projection.record,
            status=ExperimentStatus.RUNNING,
            stage=ExperimentStage.EXPLORATION,
        ),
    )
    holdout_index = next(
        index
        for index, fold in enumerate(store.folds)
        if fold.spec.fold_role is FoldRole.HOLDOUT
    )
    holdout = store.folds[holdout_index]
    store.folds[holdout_index] = replace(
        holdout,
        projection=replace(
            holdout.projection,
            status=ExperimentStatus.RUNNING,
            claim_owner_token="coordinator-a",
        ),
    )
    first_attempt = _FirstAttemptFactory().create(holdout, NOW)
    store.attempts[first_attempt.spec.attempt_id] = AttemptView(
        first_attempt.spec,
        replace(
            first_attempt.projection,
            status=ExperimentStatus.RUNNING,
            backtest_run_id=BacktestRunId("run-early-holdout"),
        ),
    )
    store.slot = SchedulerSlot(
        "global",
        store.launch.experiment_id,
        "expired-owner",
        NOW_US - 1,
        NOW_US - 10,
        NOW_US - 10,
        1,
    )
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert exc_info.value.details["reason"] == "future_stage_attempt_detected"
    assert store.claimed_keys == []


def test_terminal_holdout_work_during_exploration_fails_integrity_closed() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    store.projection = replace(
        store.projection,
        record=replace(
            store.projection.record,
            status=ExperimentStatus.RUNNING,
            stage=ExperimentStage.EXPLORATION,
        ),
    )
    holdout_index = next(
        index
        for index, fold in enumerate(store.folds)
        if fold.spec.fold_role is FoldRole.HOLDOUT
    )
    holdout = store.folds[holdout_index]
    store.folds[holdout_index] = replace(
        holdout,
        projection=replace(
            holdout.projection,
            status=ExperimentStatus.COMPLETED,
        ),
    )
    first_attempt = _FirstAttemptFactory().create(holdout, NOW)
    store.attempts[first_attempt.spec.attempt_id] = AttemptView(
        first_attempt.spec,
        replace(
            first_attempt.projection,
            status=ExperimentStatus.COMPLETED,
            backtest_run_id=BacktestRunId("run-early-terminal-holdout"),
        ),
    )
    store.slot = SchedulerSlot(
        "global",
        store.launch.experiment_id,
        "expired-owner",
        NOW_US - 1,
        NOW_US - 10,
        NOW_US - 10,
        1,
    )
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert exc_info.value.details["reason"] == "future_stage_attempt_detected"
    assert store.claimed_keys == []


@pytest.mark.parametrize(
    ("invalid_part", "reason"),
    [
        ("ordinal", "attempt_ordinal_gap"),
        ("parent", "first_attempt_invalid"),
        ("resume", "first_attempt_invalid"),
        ("checkpoint", "queued_attempt_projection_invalid"),
    ],
)
def test_existing_attempt_lineage_must_remain_valid(
    invalid_part: str,
    reason: str,
) -> None:
    store = _SchedulerStore()
    coordinator, _factory = _coordinator(store)
    dispatched = coordinator.tick(occurred_at=NOW)
    attempt_id = dispatched.dispatches[0].attempt.spec.attempt_id
    attempt = store.attempts[attempt_id]
    if invalid_part == "checkpoint":
        invalid = replace(
            attempt,
            projection=replace(
                attempt.projection,
                checkpoint_ref=CheckpointRef("checkpoint-not-task9"),
            ),
        )
    else:
        invalid = replace(
            attempt,
            spec=replace(
                attempt.spec,
                ordinal=2 if invalid_part == "ordinal" else 1,
                parent_attempt_id=(
                    AttemptId("parent-not-task9") if invalid_part == "parent" else None
                ),
                resume_from_run_id=(
                    BacktestRunId("resume-not-task9")
                    if invalid_part == "resume"
                    else None
                ),
            ),
        )
    store.attempts[attempt_id] = invalid
    write_count = len(store.write_fences)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.start_attempt(
            dispatched.dispatches[0],
            occurred_at=NOW + timedelta(seconds=1),
        )

    assert exc_info.value.details["reason"] == reason
    assert len(store.write_fences) == write_count


def test_start_attempt_returns_exact_persisted_start_and_marks_replay() -> None:
    store = _SchedulerStore()
    coordinator, _factory = _coordinator(store)
    dispatched = coordinator.tick(occurred_at=NOW).dispatches[0]

    started = coordinator.start_attempt(
        dispatched,
        occurred_at=NOW + timedelta(seconds=1),
    )
    replayed = coordinator.start_attempt(
        dispatched,
        occurred_at=NOW + timedelta(seconds=2),
    )

    assert type(started) is PersistedAttemptStart
    assert started.started_now is True
    assert started.attempt.spec == dispatched.attempt.spec
    assert started.attempt.projection.status is ExperimentStatus.RUNNING
    assert started.attempt.projection.backtest_run_id is not None
    assert started.fold.spec == dispatched.fold.spec
    assert started.fold.projection.status is ExperimentStatus.RUNNING
    assert type(replayed) is PersistedAttemptStart
    assert replayed.started_now is False
    assert replayed.attempt == started.attempt
    assert replayed.fold == started.fold


@pytest.mark.parametrize(
    ("terminal_status", "failure_code"),
    [
        (ExperimentStatus.COMPLETED, None),
        (ExperimentStatus.FAILED, ExperimentFailureCode.CANDIDATE_FAILED),
    ],
)
def test_terminal_attempt_replay_is_idempotent_and_keeps_shared_authority(
    terminal_status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
) -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    coordinator, _factory = _coordinator(store)
    dispatched = coordinator.tick(occurred_at=NOW).dispatches
    assert len(dispatched) == 2
    for item in dispatched:
        coordinator.start_attempt(item, occurred_at=NOW + timedelta(seconds=1))

    first_attempt_id = dispatched[0].attempt.spec.attempt_id
    if terminal_status is ExperimentStatus.COMPLETED:
        coordinator.complete_attempt(
            first_attempt_id,
            occurred_at=NOW + timedelta(seconds=2),
        )
    else:
        assert failure_code is not None
        coordinator.fail_attempt(
            first_attempt_id,
            failure_code,
            occurred_at=NOW + timedelta(seconds=2),
        )
    write_count = len(store.write_fences)

    replayed = coordinator.start_attempt(
        dispatched[0],
        occurred_at=NOW + timedelta(seconds=3),
    )

    assert replayed.started_now is False
    assert replayed.attempt.projection.status is terminal_status
    assert replayed.attempt.projection.failure_code is failure_code
    assert replayed.fold.projection.status is terminal_status
    assert len(store.write_fences) == write_count
    coordinator.renew_lease(occurred_at=NOW + timedelta(seconds=4))
    coordinator.complete_attempt(
        dispatched[1].attempt.spec.attempt_id,
        occurred_at=NOW + timedelta(seconds=5),
    )


@pytest.mark.parametrize(
    ("drifted_dispatch", "reason"),
    [
        (
            lambda item: replace(
                item,
                attempt=replace(
                    item.attempt,
                    spec=replace(
                        item.attempt.spec,
                        reproduction_fingerprint=ContentHash("d" * 64),
                    ),
                ),
            ),
            "dispatch_attempt_identity_drift",
        ),
        (
            lambda item: replace(
                item,
                fold=replace(
                    item.fold,
                    spec=replace(
                        item.fold.spec,
                        payload_hash=ContentHash("e" * 64),
                    ),
                ),
            ),
            "dispatch_fold_identity_drift",
        ),
        (
            lambda item: replace(item, stage=ExperimentStage.WALK_FORWARD),
            "dispatch_stage_role_mismatch",
        ),
    ],
)
def test_start_attempt_rejects_dispatch_identity_drift_before_write(
    drifted_dispatch,
    reason: str,
) -> None:
    store = _SchedulerStore()
    coordinator, _factory = _coordinator(store)
    dispatched = coordinator.tick(occurred_at=NOW).dispatches[0]
    write_count = len(store.write_fences)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.start_attempt(
            drifted_dispatch(dispatched),
            occurred_at=NOW + timedelta(seconds=1),
        )

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert exc_info.value.details["reason"] == reason
    assert len(store.write_fences) == write_count
    assert store.attempts[dispatched.attempt.spec.attempt_id].projection.status is (
        ExperimentStatus.QUEUED
    )


def test_terminal_failure_replay_rejects_a_different_failure_code() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    coordinator, _factory = _coordinator(store)
    initial = coordinator.tick(occurred_at=NOW)
    attempt_id = initial.dispatches[0].attempt.spec.attempt_id
    coordinator.start_attempt(
        initial.dispatches[0],
        occurred_at=NOW + timedelta(seconds=1),
    )
    coordinator.fail_attempt(
        attempt_id,
        ExperimentFailureCode.CANDIDATE_FAILED,
        occurred_at=NOW + timedelta(seconds=2),
    )

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.fail_attempt(
            attempt_id,
            ExperimentFailureCode.SYSTEM_ERROR,
            occurred_at=NOW + timedelta(seconds=3),
        )

    assert exc_info.value.details["reason"] == "attempt_terminal_replay_mismatch"


def test_system_failure_persists_a_fail_fast_marker_and_stops_new_dispatch() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=3)
    coordinator, _factory = _coordinator(store)
    initial = coordinator.tick(occurred_at=NOW)
    _start_all_dispatched(coordinator, initial)
    coordinator.fail_attempt(
        initial.dispatches[0].attempt.spec.attempt_id,
        ExperimentFailureCode.SYSTEM_ERROR,
        occurred_at=NOW + timedelta(seconds=3),
    )
    claim_count = len(store.claimed_keys)

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))

    assert result.state is SchedulerTickState.FAIL_FAST
    assert result.dispatches == ()
    assert len(store.claimed_keys) == claim_count
    assert result.progress is not None
    assert result.progress.hard_failure_count == 1


def test_first_attempt_contract_rejects_analysis_dto_subclasses() -> None:
    fold = _fold(1, 1, FoldRole.EXPLORATION)
    original = _FirstAttemptFactory().create(fold, NOW)
    derived = _DerivedAttemptPersistenceSpec(
        attempt_id=original.spec.attempt_id,
        fold_key=original.spec.fold_key,
        ordinal=original.spec.ordinal,
        parent_attempt_id=original.spec.parent_attempt_id,
        resume_from_run_id=original.spec.resume_from_run_id,
        reproduction_fingerprint=original.spec.reproduction_fingerprint,
        created_at=original.spec.created_at,
    )

    with pytest.raises(AppProcessError) as exc_info:
        FirstAttempt(spec=derived, projection=original.projection)

    assert exc_info.value.details["reason"] == "first_attempt_contract_invalid"


def test_scheduler_snapshot_rejects_spec_projection_lineage_drift() -> None:
    store = _SchedulerStore()
    original = store.folds[0]
    drifted_key = FoldKey(
        original.spec.key.experiment_id,
        original.spec.key.candidate_id,
        FoldId("drifted-projection-fold"),
    )
    drifted = replace(
        original,
        projection=replace(original.projection, key=drifted_key),
    )

    with pytest.raises(AppProcessError) as exc_info:
        ExperimentSchedulerSnapshot(
            projection=store.projection,
            launch_spec=store.launch,
            folds=(drifted, *store.folds[1:]),
            attempts=(),
        )

    assert exc_info.value.details["reason"] == (
        "scheduler_snapshot_fold_lineage_invalid"
    )


def test_renewed_lease_fence_is_used_by_every_later_write() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    coordinator, _factory = _coordinator(store)
    dispatched = coordinator.tick(occurred_at=NOW)

    lease = coordinator.renew_lease()
    coordinator.start_attempt(
        dispatched.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    )

    assert lease.revision == 2
    assert store.write_fences[-1] == lease.revision


def test_attempt_artifact_publication_uses_coordinator_owned_renewed_fence() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    coordinator, _factory = _coordinator(store)
    dispatched = coordinator.tick(occurred_at=NOW)
    observed: list[tuple[LeaseFence, int]] = []

    result = coordinator.publish_attempt_artifact(
        lambda fence, now_epoch_us: (
            observed.append((fence, now_epoch_us)) or "published"
        )
    )

    assert result == "published"
    assert observed[0][0].revision == 2
    assert observed[0][1] == NOW_US
    coordinator.start_attempt(
        dispatched.dispatches[0],
        occurred_at=NOW + timedelta(seconds=1),
    )
    assert store.write_fences[-1] == 2


def test_lease_authority_serializes_concurrent_result_writes() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=2)
    coordinator, _factory = _coordinator(store)
    dispatched = coordinator.tick(occurred_at=NOW)
    store.block_first_transition = True
    first, second = dispatched.dispatches

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            coordinator.start_attempt,
            first,
            occurred_at=NOW + timedelta(seconds=1),
        )
        assert store.first_transition_entered.wait(timeout=5)
        second_future = executor.submit(
            coordinator.start_attempt,
            second,
            occurred_at=NOW + timedelta(seconds=2),
        )
        assert store.max_active_writes == 1
        store.release_first_transition.set()
        first_future.result(timeout=5)
        second_future.result(timeout=5)

    assert store.max_active_writes == 1


def test_reclaimed_owner_cannot_start_the_previous_owners_attempt() -> None:
    store = _SchedulerStore()
    original, _factory = _coordinator(store, owner_token="owner-a")
    dispatched = original.tick(occurred_at=NOW)
    replacement, _replacement_factory = _coordinator(
        store,
        owner_token="owner-b",
        clock_now=NOW + timedelta(minutes=6),
    )
    recovery = replacement.tick(occurred_at=NOW + timedelta(minutes=6))

    assert recovery.state is SchedulerTickState.DISPATCHED
    assert all(item.attempt.spec.ordinal == 2 for item in recovery.dispatches)
    with pytest.raises(AppProcessError) as exc_info:
        replacement.start_attempt(
            dispatched.dispatches[0],
            occurred_at=NOW + timedelta(minutes=6, seconds=1),
        )

    assert exc_info.value.details["reason"] == "attempt_terminal_replay_invalid"


def test_reclaimed_coordinator_with_same_owner_prefix_cannot_adopt_orphan() -> None:
    store = _SchedulerStore()
    original, _factory = _coordinator(store, owner_token="shared-owner")
    original_result = original.tick(occurred_at=NOW)
    old_owner = original_result.dispatches[0].fold.projection.claim_owner_token
    replacement, _replacement_factory = _coordinator(
        store,
        owner_token="shared-owner",
        clock_now=NOW + timedelta(minutes=6),
    )

    result = replacement.tick(occurred_at=NOW + timedelta(minutes=6))

    assert result.state is SchedulerTickState.DISPATCHED
    assert result.dispatches
    assert all(
        item.fold.projection.claim_owner_token != old_owner
        and item.attempt.spec.ordinal == 2
        for item in result.dispatches
    )


def test_available_checkpoint_is_not_resumed_without_explicit_resolver() -> None:
    store = _SchedulerStore(worker_count=2, candidate_count=1)
    _set_running_stage(store, ExperimentStage.EXPLORATION)
    parent_fold = next(
        item for item in store.folds if item.spec.fold_role is FoldRole.EXPLORATION
    )
    queued = _FirstAttemptFactory().create(parent_fold, NOW)
    parent_run_id = BacktestRunId("research-run-nonresumable")
    parent = AttemptView(
        queued.spec,
        replace(
            queued.projection,
            status=ExperimentStatus.CANCELLED,
            backtest_run_id=parent_run_id,
            checkpoint_ref=CheckpointRef(str(parent_run_id)),
        ),
    )
    store.attempts[parent.spec.attempt_id] = parent
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_FirstAttemptFactory(),
        owner_token="replacement-owner",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW,
        checkpoint_available=lambda run_id: run_id == str(parent_run_id),
    )

    result = coordinator.tick(occurred_at=NOW)

    successor = next(
        item.attempt
        for item in result.dispatches
        if item.attempt.spec.parent_attempt_id == parent.spec.attempt_id
    )
    assert successor.spec.resume_from_run_id is None


def test_reclaimed_owner_cannot_finish_the_previous_owners_running_attempt() -> None:
    store = _SchedulerStore()
    original, _factory = _coordinator(store, owner_token="owner-a")
    dispatched = original.tick(occurred_at=NOW)
    attempt_id = dispatched.dispatches[0].attempt.spec.attempt_id
    original.start_attempt(
        dispatched.dispatches[0],
        occurred_at=NOW + timedelta(seconds=1),
    )
    replacement, _replacement_factory = _coordinator(
        store,
        owner_token="owner-b",
        clock_now=NOW + timedelta(minutes=6),
    )
    recovery = replacement.tick(occurred_at=NOW + timedelta(minutes=6))

    assert recovery.state is SchedulerTickState.DISPATCHED
    assert store.attempts[attempt_id].projection.failure_code is (
        ExperimentFailureCode.LEASE_LOST
    )
    with pytest.raises(AppProcessError) as exc_info:
        replacement.complete_attempt(
            attempt_id,
            occurred_at=NOW + timedelta(minutes=6, seconds=1),
        )

    assert exc_info.value.details["reason"] == "attempt_is_not_finishable"


def test_split_terminal_write_stops_for_task10_recovery_after_lease_loss() -> None:
    store = _SchedulerStore()
    original, _factory = _coordinator(store, owner_token="owner-a")
    dispatched = original.tick(occurred_at=NOW)
    attempt_id = dispatched.dispatches[0].attempt.spec.attempt_id
    original.start_attempt(
        dispatched.dispatches[0],
        occurred_at=NOW + timedelta(seconds=1),
    )
    store.raise_lease_lost_on_fold_transition = True

    with pytest.raises(AppProcessError) as exc_info:
        original.complete_attempt(
            attempt_id,
            occurred_at=NOW + timedelta(seconds=2),
        )
    store.raise_lease_lost_on_fold_transition = False
    claim_count = len(store.claimed_keys)
    replacement, _replacement_factory = _coordinator(
        store,
        owner_token="owner-b",
        clock_now=NOW + timedelta(minutes=6),
    )

    result = replacement.tick(occurred_at=NOW + timedelta(minutes=6))

    assert exc_info.value.details["code"] == "LEASE_LOST"
    assert result.state is SchedulerTickState.DISPATCHED
    assert store.attempts[attempt_id].projection.status is ExperimentStatus.COMPLETED
    completed_fold = next(
        item
        for item in store.folds
        if item.spec.key == dispatched.dispatches[0].fold.spec.key
    )
    assert completed_fold.projection.status is ExperimentStatus.COMPLETED
    assert all(
        item.fold.spec.key != completed_fold.spec.key for item in result.dispatches
    )
    assert len(store.claimed_keys) > claim_count


def test_lost_lease_invalidates_coordinator_and_stops_all_later_writes() -> None:
    store = _SchedulerStore()
    store.raise_lease_lost_on_claim = True
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)
    store.raise_lease_lost_on_claim = False
    write_count = len(store.write_fences)

    with pytest.raises(AppProcessError) as second_exc:
        coordinator.tick(occurred_at=NOW + timedelta(seconds=1))

    assert exc_info.value.details["code"] == "LEASE_LOST"
    assert second_exc.value.details["code"] == "LEASE_LOST"
    assert len(store.write_fences) == write_count


def test_integrity_failure_fails_closed_and_permanently_stops_dispatch() -> None:
    store = _SchedulerStore()
    store.raise_integrity_failure_on_claim = True
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)
    store.raise_integrity_failure_on_claim = False
    claim_count = len(store.claimed_keys)

    with pytest.raises(AppProcessError) as second_exc:
        coordinator.tick(occurred_at=NOW + timedelta(seconds=1))

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert second_exc.value.details["code"] == "LEASE_LOST"
    assert len(store.claimed_keys) == claim_count


def test_queue_read_integrity_failure_permanently_invalidates_authority() -> None:
    store = _SchedulerStore()
    store.raise_integrity_on_slot_read = True
    coordinator, _factory = _coordinator(store)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)
    store.raise_integrity_on_slot_read = False

    with pytest.raises(AppProcessError) as second_exc:
        coordinator.tick(occurred_at=NOW + timedelta(seconds=1))

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert second_exc.value.details["code"] == "LEASE_LOST"


def test_stale_event_timestamp_cannot_extend_an_expired_physical_lease() -> None:
    store = _SchedulerStore()
    clock = _MutableClock(NOW)
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_FirstAttemptFactory(),
        owner_token="clock-owner",
        lease_duration=timedelta(minutes=5),
        clock=clock,
    )
    dispatched = coordinator.tick(occurred_at=NOW)
    clock.current = NOW + timedelta(minutes=6)
    write_count = len(store.write_fences)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.start_attempt(
            dispatched.dispatches[0],
            occurred_at=NOW,
        )

    assert exc_info.value.details["code"] == "LEASE_LOST"
    assert len(store.write_fences) == write_count


def test_retry_fold_fails_closed_when_scheduler_slot_busy() -> None:
    """Control-route retry fails closed (LEASE_LOST) when the slot is leased."""
    store = _SchedulerStore()
    store.slot = SchedulerSlot(
        "global",
        ExperimentId("experiment-1"),
        "tick-owner",
        NOW_US + 1_000_000,
        NOW_US,
        NOW_US,
        0,
    )
    coordinator, _ = _coordinator(store)
    with pytest.raises(AppProcessError) as info:
        coordinator.retry_fold(
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_id="fold-1-1",
            expected_revision=0,
            occurred_at=NOW,
        )
    details = info.value.details
    assert details["code"] == "LEASE_LOST"
    assert details["reason"] == "scheduler_slot_busy"


def _set_evidence_stage_with_terminal_folds(store: _SchedulerStore) -> None:
    """Promote ``store`` into EVIDENCE with every prior fold marked terminal."""
    _set_running_stage(store, ExperimentStage.EVIDENCE)
    for index, fold in enumerate(store.folds):
        store.folds[index] = replace(
            fold,
            projection=replace(
                fold.projection,
                status=ExperimentStatus.COMPLETED,
            ),
        )


def test_evidence_stage_collects_and_transitions_to_completed() -> None:
    store = _SchedulerStore()
    _set_evidence_stage_with_terminal_folds(store)
    collector = _FakeEvidenceCollector()
    coordinator, _factory = _coordinator(store, evidence_collector=collector)

    result = coordinator.tick(occurred_at=NOW)

    assert result.state is SchedulerTickState.COMPLETED
    assert result.dispatches == ()
    assert store.projection.record.status is ExperimentStatus.COMPLETED
    assert store.projection.record.stage is ExperimentStage.EVIDENCE
    assert len(collector.collect_calls) == 1
    call = collector.collect_calls[0]
    assert call["experiment_id"] == store.launch.experiment_id
    assert call["created_at"] == NOW
    assert call["now_epoch_us"] == NOW_US
    assert call["lease_fence"] is not None
    assert len(store.controlled_transitions) == 1
    transition = store.controlled_transitions[0]
    assert transition["target_status"] is ExperimentStatus.COMPLETED
    assert transition["target_stage"] is ExperimentStage.EVIDENCE
    assert transition["reason_code"] == "evidence_collection_completed"
    assert transition["attempt_started"] is False


def test_evidence_stage_fail_fast_on_collector_error() -> None:
    store = _SchedulerStore()
    _set_evidence_stage_with_terminal_folds(store)
    collector_error = AppProcessError(
        "collector failed",
        details={"code": "SPEC_INVALID", "reason": "preflight_passed_event_not_found"},
    )
    collector = _FakeEvidenceCollector(raise_error=collector_error)
    coordinator, _factory = _coordinator(store, evidence_collector=collector)

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW)

    assert exc_info.value is collector_error
    assert store.projection.record.status is ExperimentStatus.RUNNING
    assert store.projection.record.stage is ExperimentStage.EVIDENCE
    assert len(collector.collect_calls) == 1
    assert store.controlled_transitions == []


def test_evidence_no_op_when_collector_not_configured() -> None:
    store = _SchedulerStore()
    _set_evidence_stage_with_terminal_folds(store)
    coordinator, _factory = _coordinator(store, evidence_collector=None)

    result = coordinator.tick(occurred_at=NOW)

    assert result.state is SchedulerTickState.WAITING
    assert result.dispatches == ()
    assert store.projection.record.status is ExperimentStatus.RUNNING
    assert store.projection.record.stage is ExperimentStage.EVIDENCE
    assert store.controlled_transitions == []


def test_retry_fold_releases_transient_lease_when_fold_not_failed() -> None:
    """Control-route retry releases the transient lease even when recovery rejects."""
    store = _SchedulerStore()
    coordinator, _ = _coordinator(store)
    with pytest.raises(AppProcessError) as info:
        coordinator.retry_fold(
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_id="fold-1-1",
            expected_revision=0,
            occurred_at=NOW,
        )
    details = info.value.details
    assert details["code"] == "SPEC_INVALID"
    assert details["reason"] == "terminal_fold_retry_requires_failed_fold"
    assert store.slot.owner_token is None
