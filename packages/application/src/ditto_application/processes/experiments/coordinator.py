"""Durable, lease-fenced first-attempt scheduling for R3 experiments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    AttemptId,
    AttemptView,
    BacktestRunId,
    ContentHash,
    ExperimentFailureCode,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldKey,
    FoldRole,
    FoldView,
    SchedulerLease,
    canonical_payload,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import (
    _coordinator_snapshot as _snapshot_rules,
)
from ditto_application.processes.experiments.lease_authority import LeaseAuthority
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStoreProtocol,
    FirstAttempt,
    FirstAttemptFactory,
)

__all__ = [
    "ExperimentDispatch",
    "ExperimentExecutionCoordinator",
    "ExperimentProgress",
    "PersistedAttemptStart",
    "SchedulerTickResult",
    "SchedulerTickState",
    "deterministic_backtest_run_id",
]

_LIVE = frozenset({ExperimentStatus.QUEUED, ExperimentStatus.RUNNING})
_TERMINAL_WORK = frozenset(
    {
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
    }
)
_TERMINAL_EXPERIMENT = frozenset(
    {*_TERMINAL_WORK, ExperimentStatus.COMPLETED_WITH_FAILURES}
)
_HARD_FAILURES = frozenset(
    {
        ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ExperimentFailureCode.SYSTEM_ERROR,
    }
)
_FIRST_RUN_FAILURES = frozenset(
    {ExperimentFailureCode.CANDIDATE_FAILED, *_HARD_FAILURES}
)
_REPLAYABLE_TERMINAL_ATTEMPT = frozenset(
    {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED}
)
_STAGE_ROLE = {
    ExperimentStage.EXPLORATION: FoldRole.EXPLORATION,
    ExperimentStage.WALK_FORWARD: FoldRole.WALK_FORWARD,
}
_NEXT_STAGE = {
    ExperimentStage.EXPLORATION: ExperimentStage.WALK_FORWARD,
    ExperimentStage.WALK_FORWARD: ExperimentStage.CANDIDATE_SELECTION,
}
_SNAPSHOT_VOCABULARY = _snapshot_rules.SnapshotVocabulary(
    live_statuses=_LIVE,
    terminal_work_statuses=_TERMINAL_WORK,
    hard_failure_codes=_HARD_FAILURES,
    first_run_failure_codes=_FIRST_RUN_FAILURES,
    replayable_terminal_statuses=_REPLAYABLE_TERMINAL_ATTEMPT,
    failed_status=ExperimentStatus.FAILED,
    queued_status=ExperimentStatus.QUEUED,
    running_status=ExperimentStatus.RUNNING,
    cancelled_status=ExperimentStatus.CANCELLED,
    candidate_failed_code=ExperimentFailureCode.CANDIDATE_FAILED,
    fail_fast_policy=ExperimentFailurePolicy.FAIL_FAST,
    stage_role=_snapshot_rules.erase_mapping_keys(_STAGE_ROLE),
    role_order=_snapshot_rules.erase_mapping_keys(
        {
            FoldRole.EXPLORATION: 0,
            FoldRole.WALK_FORWARD: 1,
            FoldRole.HOLDOUT: 2,
        },
    ),
    stage_role_ceiling=_snapshot_rules.erase_mapping_keys(
        {
            ExperimentStage.EXPLORATION: 0,
            ExperimentStage.WALK_FORWARD: 1,
            ExperimentStage.CANDIDATE_SELECTION: 1,
            ExperimentStage.HOLDOUT: 2,
            ExperimentStage.EVIDENCE: 2,
        },
    ),
    prior_fold_roles=_snapshot_rules.erase_mapping_keys(
        {
            ExperimentStage.PREFLIGHT: (),
            ExperimentStage.EXPLORATION: (),
            ExperimentStage.WALK_FORWARD: (FoldRole.EXPLORATION,),
            ExperimentStage.CANDIDATE_SELECTION: (
                FoldRole.EXPLORATION,
                FoldRole.WALK_FORWARD,
            ),
            ExperimentStage.HOLDOUT: (
                FoldRole.EXPLORATION,
                FoldRole.WALK_FORWARD,
            ),
            ExperimentStage.EVIDENCE: (
                FoldRole.EXPLORATION,
                FoldRole.WALK_FORWARD,
                FoldRole.HOLDOUT,
            ),
        },
    ),
)
_scheduler_error = _snapshot_rules.scheduler_error


class SchedulerTickState(StrEnum):
    """Observable result of one bounded coordinator tick."""

    IDLE = "idle"
    LEASE_BUSY = "lease_busy"
    DISPATCHED = "dispatched"
    WAITING = "waiting"
    CANDIDATE_SELECTION = "candidate_selection"
    HOLDOUT_GATED = "holdout_gated"
    RECOVERY_REQUIRED = "recovery_required"
    FAIL_FAST = "fail_fast"


@dataclass(frozen=True, slots=True)
class ExperimentProgress:
    """Progress calculated only from persisted fold and attempt projections."""

    experiment_id: ExperimentId
    stage: ExperimentStage
    worker_limit: int
    available_capacity: int
    total_fold_count: int
    terminal_fold_count: int
    live_attempt_count: int
    completed_attempt_count: int
    failed_candidate_attempt_count: int
    hard_failure_count: int


@dataclass(frozen=True, slots=True)
class ExperimentDispatch:
    """One durably claimed first attempt ready for execution-owned audit work."""

    stage: ExperimentStage
    fold: FoldView
    attempt: AttemptView


@dataclass(frozen=True, slots=True)
class PersistedAttemptStart:
    """Exact durable attempt/fold pair observed by a start-attempt request."""

    attempt: AttemptView
    fold: FoldView
    started_now: bool

    def __post_init__(self) -> None:
        """Reject incomplete or internally inconsistent persisted start facts."""
        base_invalid = (
            type(self.attempt) is not AttemptView
            or type(self.fold) is not FoldView
            or type(self.started_now) is not bool
            or self.attempt.spec.attempt_id != self.attempt.projection.attempt_id
            or self.fold.spec.key != self.fold.projection.key
            or self.attempt.spec.fold_key != self.fold.spec.key
            or self.attempt.projection.backtest_run_id is None
            or self.attempt.projection.checkpoint_ref is not None
        )
        running = (
            self.attempt.projection.status is ExperimentStatus.RUNNING
            and self.attempt.projection.failure_code is None
            and self.fold.projection.status is ExperimentStatus.RUNNING
            and self.fold.projection.claim_owner_token is not None
        )
        terminal_status = self.attempt.projection.status
        terminal = (
            not self.started_now
            and terminal_status in _REPLAYABLE_TERMINAL_ATTEMPT
            and self.fold.projection.status is terminal_status
            and self.fold.projection.claim_owner_token is None
            and (
                (
                    terminal_status is ExperimentStatus.COMPLETED
                    and self.attempt.projection.failure_code is None
                )
                or (
                    terminal_status is ExperimentStatus.FAILED
                    and self.attempt.projection.failure_code in _FIRST_RUN_FAILURES
                )
            )
        )
        if base_invalid or not (running or terminal):
            raise _scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "persisted_attempt_start_invalid",
            )


@dataclass(frozen=True, slots=True)
class SchedulerTickResult:
    """Bounded result of one tick; absence of progress means no owned experiment."""

    state: SchedulerTickState
    experiment_id: ExperimentId | None
    dispatches: tuple[ExperimentDispatch, ...]
    progress: ExperimentProgress | None


class ExperimentExecutionCoordinator:
    """Coordinate only durable first-run work under one singleton lease."""

    def __init__(
        self,
        *,
        store: ExperimentSchedulerStoreProtocol,
        first_attempt_factory: FirstAttemptFactory,
        owner_token: str,
        lease_duration: timedelta,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._first_attempt_factory = first_attempt_factory
        self._authority = LeaseAuthority(
            store,
            owner_token=owner_token,
            lease_duration=lease_duration,
            clock=clock,
        )

    def tick(self, *, occurred_at: datetime) -> SchedulerTickResult:
        """Acquire the queue head and dispatch at most DB-derived capacity."""
        _require_utc_event_time(occurred_at)
        self._authority.ensure_usable()
        if not self._authority.has_lease:
            unowned = self._acquire_queue_head()
            if unowned is not None:
                return unowned
        return self._authority.execute(
            lambda lease, now_epoch_us: self._tick_owned(
                lease,
                now_epoch_us,
                occurred_at,
            )
        )

    def renew_lease(self, *, occurred_at: datetime | None = None) -> SchedulerLease:
        """Renew from the authority clock; retain worker-call compatibility."""
        if occurred_at is not None:
            _require_utc_event_time(occurred_at)
        return self._authority.renew()

    def start_attempt(
        self,
        dispatch: ExperimentDispatch,
        *,
        occurred_at: datetime,
    ) -> PersistedAttemptStart:
        """Validate the exact dispatch and persist its derived run identity."""
        _require_utc_event_time(occurred_at)
        if type(dispatch) is not ExperimentDispatch:
            raise _scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "invalid_experiment_dispatch",
            )

        def operation(
            lease: SchedulerLease,
            now_epoch_us: Callable[[], int],
        ) -> PersistedAttemptStart:
            snapshot = self._load_snapshot(lease.experiment_id)
            matches = tuple(
                item
                for item in snapshot.attempts
                if item.spec.attempt_id == dispatch.attempt.spec.attempt_id
            )
            if len(matches) != 1:
                raise _scheduler_error(
                    "EXPERIMENT_INTEGRITY_FAILED",
                    "dispatch_attempt_identity_drift",
                )
            attempt = matches[0]
            _require_task9_first_attempt(attempt)
            fold = _find_fold(snapshot, attempt.spec.fold_key)
            backtest_run_id = deterministic_backtest_run_id(
                attempt.spec.attempt_id,
                attempt.spec.reproduction_fingerprint,
            )
            if attempt.projection.status in _REPLAYABLE_TERMINAL_ATTEMPT:
                _snapshot_rules.require_exact_terminal_replay(
                    dispatch,
                    attempt,
                    fold,
                    backtest_run_id,
                    _SNAPSHOT_VOCABULARY,
                )
                return PersistedAttemptStart(attempt, fold, False)
            fold = _require_fold_owned_by_lease(snapshot, attempt, lease)
            _snapshot_rules.require_exact_persisted_dispatch(
                snapshot,
                dispatch,
                attempt,
                fold,
                lease,
                _SNAPSHOT_VOCABULARY,
            )
            if attempt.projection.status is ExperimentStatus.RUNNING:
                if attempt.projection.backtest_run_id == backtest_run_id:
                    return PersistedAttemptStart(attempt, fold, False)
                raise _scheduler_error("SPEC_INVALID", "attempt_run_identity_drift")
            if attempt.projection.status is not ExperimentStatus.QUEUED:
                raise _scheduler_error("SPEC_INVALID", "attempt_is_not_startable")
            started = self._store.transition_attempt(
                attempt,
                target_status=ExperimentStatus.RUNNING,
                backtest_run_id=backtest_run_id,
                failure_code=None,
                lease=lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
            return PersistedAttemptStart(started, fold, True)

        return self._authority.execute(operation)

    def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        occurred_at: datetime,
    ) -> ExperimentProgress:
        """Persist one successful attempt and its fold under one serialized fence."""
        _require_utc_event_time(occurred_at)
        return self._authority.execute(
            lambda lease, now_epoch_us: self._finish_attempt(
                lease,
                now_epoch_us,
                occurred_at,
                attempt_id,
                ExperimentStatus.COMPLETED,
                None,
            ),
        )

    def fail_attempt(
        self,
        attempt_id: AttemptId,
        failure_code: ExperimentFailureCode,
        *,
        occurred_at: datetime,
    ) -> ExperimentProgress:
        """Persist a local or hard first-run failure without dispatching retries."""
        _require_utc_event_time(occurred_at)
        if failure_code not in _FIRST_RUN_FAILURES:
            raise _scheduler_error("SPEC_INVALID", "unsupported_first_run_failure")
        return self._authority.execute(
            lambda lease, now_epoch_us: self._finish_attempt(
                lease,
                now_epoch_us,
                occurred_at,
                attempt_id,
                ExperimentStatus.FAILED,
                failure_code,
            ),
        )

    def _acquire_queue_head(self) -> SchedulerTickResult | None:
        try:
            slot = self._store.get_scheduler_slot()
            now_epoch_us = self._authority.now_epoch_us()
            if (
                slot.experiment_id is not None
                and slot.lease_until_epoch_us is not None
                and slot.lease_until_epoch_us > now_epoch_us
            ):
                return _empty_result(SchedulerTickState.LEASE_BUSY)
            queue = self._store.list_dispatchable_experiments()
            selected: ExperimentSchedulerSnapshot | None = None
            if slot.experiment_id is not None:
                occupant = self._load_snapshot(slot.experiment_id)
                if occupant.projection.record.status not in _TERMINAL_EXPERIMENT:
                    selected = occupant
            if selected is None:
                if not queue:
                    return _empty_result(SchedulerTickState.IDLE)
                selected = self._load_snapshot(queue[0].record.experiment_id)
            _snapshot_rules.validate_worker_limit(selected)
            experiment_id = selected.projection.record.experiment_id
            acquired = self._authority.acquire(
                experiment_id,
                expected_revision=slot.revision,
            )
        except AppProcessError:
            raise
        except AnalysisError as exc:
            raise self._authority.fail_closed(exc) from exc
        if not acquired:
            return _empty_result(SchedulerTickState.LEASE_BUSY)
        return None

    def _tick_owned(
        self,
        lease: SchedulerLease,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> SchedulerTickResult:
        snapshot = self._load_snapshot(lease.experiment_id)
        _snapshot_rules.validate_worker_limit(snapshot)
        for attempt in snapshot.attempts:
            _require_task9_first_attempt(attempt)
        if snapshot.projection.record.status is ExperimentStatus.QUEUED:
            self._store.transition_to_running(
                snapshot.projection,
                lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
            snapshot = self._load_snapshot(lease.experiment_id)
        if snapshot.projection.record.status is not ExperimentStatus.RUNNING:
            return _result(SchedulerTickState.WAITING, snapshot, ())
        _snapshot_rules.validate_live_work_stage(snapshot, _SNAPSHOT_VOCABULARY)
        _snapshot_rules.validate_no_future_stage_outcomes(
            snapshot,
            _SNAPSHOT_VOCABULARY,
        )
        _snapshot_rules.validate_stage_frontier(snapshot, _SNAPSHOT_VOCABULARY)
        if _snapshot_rules.requires_recovery(
            snapshot,
            lease.owner_token,
            _SNAPSHOT_VOCABULARY,
        ):
            return _result(SchedulerTickState.RECOVERY_REQUIRED, snapshot, ())
        if _snapshot_rules.must_stop_after_failure(
            snapshot,
            _SNAPSHOT_VOCABULARY,
        ):
            return _result(SchedulerTickState.FAIL_FAST, snapshot, ())
        snapshot = self._isolate_failed_candidates(
            snapshot,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )
        snapshot, terminal_state = self._advance_completed_stages(
            snapshot,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )
        if terminal_state is not None:
            return _result(terminal_state, snapshot, ())
        dispatches = self._dispatch_capacity(
            snapshot,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )
        refreshed = self._load_snapshot(lease.experiment_id)
        state = (
            SchedulerTickState.DISPATCHED if dispatches else SchedulerTickState.WAITING
        )
        return _result(state, refreshed, dispatches)

    def _isolate_failed_candidates(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> ExperimentSchedulerSnapshot:
        failed_candidates = _snapshot_rules.candidate_failure_ids(
            snapshot,
            _SNAPSHOT_VOCABULARY,
        )
        if not failed_candidates:
            return snapshot
        for fold in snapshot.folds:
            if (
                fold.spec.key.candidate_id in failed_candidates
                and fold.projection.status is ExperimentStatus.QUEUED
            ):
                self._store.transition_fold(
                    fold,
                    target_status=ExperimentStatus.CANCELLED,
                    failure_code=None,
                    lease=lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                )
        return self._load_snapshot(lease.experiment_id)

    def _advance_completed_stages(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> tuple[ExperimentSchedulerSnapshot, SchedulerTickState | None]:
        for _step in range(2):
            stage = snapshot.projection.record.stage
            if stage is ExperimentStage.CANDIDATE_SELECTION:
                return snapshot, SchedulerTickState.CANDIDATE_SELECTION
            if stage is ExperimentStage.HOLDOUT:
                return snapshot, SchedulerTickState.HOLDOUT_GATED
            if stage is ExperimentStage.EVIDENCE:
                return snapshot, SchedulerTickState.WAITING
            role = _STAGE_ROLE.get(stage)
            if role is None:
                raise _scheduler_error("SPEC_INVALID", "running_stage_not_dispatchable")
            stage_folds = tuple(
                fold for fold in snapshot.folds if fold.spec.fold_role is role
            )
            if not stage_folds:
                raise _scheduler_error("SPEC_INVALID", "stage_has_no_persisted_folds")
            if any(fold.projection.status in _LIVE for fold in stage_folds):
                return snapshot, None
            if any(
                fold.projection.status not in _TERMINAL_WORK for fold in stage_folds
            ):
                raise _scheduler_error("SPEC_INVALID", "stage_fold_status_invalid")
            target_stage = _NEXT_STAGE[stage]
            self._store.advance_stage(
                snapshot.projection,
                target_stage,
                lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
            snapshot = self._load_snapshot(lease.experiment_id)
        return snapshot, None

    def _dispatch_capacity(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> tuple[ExperimentDispatch, ...]:
        progress = _progress(snapshot)
        role = _STAGE_ROLE[snapshot.projection.record.stage]
        candidate_ordinals = {
            candidate.candidate_id: candidate.ordinal
            for candidate in snapshot.launch_spec.candidates
        }
        claimable = sorted(
            (
                fold
                for fold in snapshot.folds
                if fold.spec.fold_role is role
                and fold.projection.status is ExperimentStatus.QUEUED
            ),
            key=lambda fold: (
                candidate_ordinals[fold.spec.key.candidate_id],
                fold.spec.ordinal,
                str(fold.spec.key.fold_id),
            ),
        )
        dispatches: list[ExperimentDispatch] = []
        for fold in claimable[: progress.available_capacity]:
            first_attempt = self._first_attempt_factory.create(fold, occurred_at)
            if type(first_attempt) is not FirstAttempt:
                raise _scheduler_error("SPEC_INVALID", "first_attempt_factory_invalid")
            claimed_fold, attempt = self._store.claim_first_attempt(
                fold,
                first_attempt,
                lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
            dispatches.append(
                ExperimentDispatch(
                    stage=snapshot.projection.record.stage,
                    fold=claimed_fold,
                    attempt=attempt,
                )
            )
        return tuple(dispatches)

    def _finish_attempt(
        self,
        lease: SchedulerLease,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
        attempt_id: AttemptId,
        target_status: ExperimentStatus,
        failure_code: ExperimentFailureCode | None,
    ) -> ExperimentProgress:
        snapshot = self._load_snapshot(lease.experiment_id)
        attempt = _find_attempt(snapshot, attempt_id)
        _require_task9_first_attempt(attempt)
        fold = _find_fold(snapshot, attempt.spec.fold_key)
        if attempt.projection.status is target_status:
            if attempt.projection.failure_code is not failure_code:
                raise _scheduler_error(
                    "SPEC_INVALID",
                    "attempt_terminal_replay_mismatch",
                )
            if fold.projection.status is target_status:
                return _progress(snapshot)
            _require_fold_owned_by_lease(snapshot, attempt, lease)
            updated_attempt = attempt
        else:
            _require_fold_owned_by_lease(snapshot, attempt, lease)
            if attempt.projection.status is not ExperimentStatus.RUNNING:
                raise _scheduler_error("SPEC_INVALID", "attempt_is_not_finishable")
            if attempt.projection.backtest_run_id is None:
                raise _scheduler_error("SPEC_INVALID", "attempt_run_identity_missing")
            updated_attempt = self._store.transition_attempt(
                attempt,
                target_status=target_status,
                backtest_run_id=attempt.projection.backtest_run_id,
                failure_code=failure_code,
                lease=lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
        snapshot = self._load_snapshot(lease.experiment_id)
        fold = _find_fold(snapshot, updated_attempt.spec.fold_key)
        if fold.projection.status is target_status:
            return _progress(snapshot)
        if fold.projection.status is not ExperimentStatus.RUNNING:
            raise _scheduler_error("SPEC_INVALID", "attempt_fold_is_not_finishable")
        self._store.transition_fold(
            fold,
            target_status=target_status,
            failure_code=failure_code,
            lease=lease,
            now_epoch_us=now_epoch_us(),
            occurred_at=occurred_at,
        )
        return _progress(self._load_snapshot(lease.experiment_id))

    def _load_snapshot(
        self,
        experiment_id: ExperimentId,
    ) -> ExperimentSchedulerSnapshot:
        snapshot = self._store.load_snapshot(experiment_id)
        _snapshot_rules.validate_durable_worker_capacity(
            snapshot,
            _SNAPSHOT_VOCABULARY,
        )
        return snapshot


def _find_attempt(
    snapshot: ExperimentSchedulerSnapshot,
    attempt_id: AttemptId,
) -> AttemptView:
    matches = tuple(
        attempt
        for attempt in snapshot.attempts
        if attempt.spec.attempt_id == attempt_id
    )
    if len(matches) != 1:
        raise _scheduler_error("SPEC_INVALID", "attempt_not_found_or_ambiguous")
    return matches[0]


def deterministic_backtest_run_id(
    attempt_id: AttemptId,
    reproduction_fingerprint: ContentHash,
) -> BacktestRunId:
    """Derive the stable run identity from the exact attempt fingerprint."""
    identity = canonical_payload(
        {
            "kind": "r3_research_backtest_run",
            "attempt_id": str(attempt_id),
            "reproduction_fingerprint": str(reproduction_fingerprint),
        }
    ).content_hash
    return BacktestRunId(f"research-run-{identity}")


def _require_fold_owned_by_lease(
    snapshot: ExperimentSchedulerSnapshot,
    attempt: AttemptView,
    lease: SchedulerLease,
) -> FoldView:
    fold = _find_fold(snapshot, attempt.spec.fold_key)
    if (
        fold.projection.status is not ExperimentStatus.RUNNING
        or fold.projection.claim_owner_token != lease.owner_token
    ):
        raise _scheduler_error(
            "LEASE_LOST",
            "attempt_fold_not_owned_by_lease",
        )
    return fold


def _find_fold(snapshot: ExperimentSchedulerSnapshot, key: FoldKey) -> FoldView:
    matches = tuple(fold for fold in snapshot.folds if fold.spec.key == key)
    if len(matches) != 1:
        raise _scheduler_error("SPEC_INVALID", "fold_not_found_or_ambiguous")
    return matches[0]


def _require_task9_first_attempt(attempt: AttemptView) -> None:
    if (
        attempt.spec.attempt_id != attempt.projection.attempt_id
        or attempt.spec.ordinal != 1
        or attempt.spec.parent_attempt_id is not None
        or attempt.spec.resume_from_run_id is not None
        or attempt.projection.checkpoint_ref is not None
    ):
        raise _scheduler_error(
            "SPEC_INVALID",
            "task9_first_attempt_contract_invalid",
        )


def _progress(snapshot: ExperimentSchedulerSnapshot) -> ExperimentProgress:
    _snapshot_rules.validate_durable_worker_capacity(
        snapshot,
        _SNAPSHOT_VOCABULARY,
    )
    worker_limit = snapshot.launch_spec.worker_count
    live_attempts = tuple(
        attempt for attempt in snapshot.attempts if attempt.projection.status in _LIVE
    )
    return ExperimentProgress(
        experiment_id=snapshot.projection.record.experiment_id,
        stage=snapshot.projection.record.stage,
        worker_limit=worker_limit,
        available_capacity=max(0, worker_limit - len(live_attempts)),
        total_fold_count=len(snapshot.folds),
        terminal_fold_count=sum(
            1 for fold in snapshot.folds if fold.projection.status in _TERMINAL_WORK
        ),
        live_attempt_count=len(live_attempts),
        completed_attempt_count=sum(
            1
            for attempt in snapshot.attempts
            if attempt.projection.status is ExperimentStatus.COMPLETED
        ),
        failed_candidate_attempt_count=sum(
            1
            for attempt in snapshot.attempts
            if attempt.projection.failure_code is ExperimentFailureCode.CANDIDATE_FAILED
        ),
        hard_failure_count=_snapshot_rules.hard_failure_count(
            snapshot,
            _SNAPSHOT_VOCABULARY,
        ),
    )


def _result(
    state: SchedulerTickState,
    snapshot: ExperimentSchedulerSnapshot,
    dispatches: tuple[ExperimentDispatch, ...],
) -> SchedulerTickResult:
    return SchedulerTickResult(
        state=state,
        experiment_id=snapshot.projection.record.experiment_id,
        dispatches=dispatches,
        progress=_progress(snapshot),
    )


def _empty_result(state: SchedulerTickState) -> SchedulerTickResult:
    return SchedulerTickResult(state, None, (), None)


def _require_utc_event_time(value: datetime) -> None:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise _scheduler_error("SPEC_INVALID", "occurred_at_must_be_utc")
