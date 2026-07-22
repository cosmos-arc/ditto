"""Durable, lease-fenced first-attempt scheduling for R3 experiments."""

# ruff: noqa: PLR0913

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    AttemptId,
    AttemptView,
    CheckpointRef,
    ExperimentFailureCode,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldRole,
    SchedulerLease,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import (
    _coordinator_snapshot as _snapshot_rules,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
    ExperimentDispatch,
    ExperimentProgress,
    PersistedAttemptStart,
    SchedulerTickResult,
    SchedulerTickState,
)
from ditto_application.processes.experiments._coordinator_holdout import (
    HoldoutCoordinatorAuthority,
    selected_holdout_fold_ids,
    validate_holdout_snapshot,
)
from ditto_application.processes.experiments._coordinator_progress import (
    CoordinatorResultBuilder,
)
from ditto_application.processes.experiments._coordinator_recovery import (
    ExperimentRecoveryOrchestrator,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    deterministic_backtest_run_id,
)
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
    HoldoutClaimReceipt,
    HoldoutSelectionEvidenceProvider,
)
from ditto_application.processes.experiments.lease_authority import (
    LeaseAuthority,
    require_utc_event_time,
    run_unfenced_scheduler_operation,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStoreProtocol,
    FirstAttemptFactory,
    ResearchExecutionDirective,
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
_TERMINAL_EXPERIMENT = _TERMINAL_WORK | {
    ExperimentStatus.COMPLETED_WITH_FAILURES,
}
_HARD_FAILURES = frozenset(
    {
        ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ExperimentFailureCode.SYSTEM_ERROR,
    }
)
_FIRST_RUN_FAILURES = _HARD_FAILURES | {ExperimentFailureCode.CANDIDATE_FAILED}
_REPLAYABLE_TERMINAL_ATTEMPT = frozenset(
    {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED}
)
_STAGE_ROLE = {
    ExperimentStage.EXPLORATION: FoldRole.EXPLORATION,
    ExperimentStage.WALK_FORWARD: FoldRole.WALK_FORWARD,
    ExperimentStage.HOLDOUT: FoldRole.HOLDOUT,
}
_NEXT_STAGE = {
    ExperimentStage.EXPLORATION: ExperimentStage.WALK_FORWARD,
    ExperimentStage.WALK_FORWARD: ExperimentStage.CANDIDATE_SELECTION,
    ExperimentStage.HOLDOUT: ExperimentStage.EVIDENCE,
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
_require_utc_event_time = require_utc_event_time
_RESULT_BUILDER = CoordinatorResultBuilder(_SNAPSHOT_VOCABULARY)
_progress = _RESULT_BUILDER.progress
_result = _RESULT_BUILDER.result
_empty_result = _RESULT_BUILDER.empty


class ExperimentExecutionCoordinator:
    """Coordinate only durable first-run work under one singleton lease."""

    def __init__(
        self,
        *,
        store: ExperimentSchedulerStoreProtocol,
        first_attempt_factory: FirstAttemptFactory,
        owner_token: str,
        lease_duration: timedelta,
        selection_evidence_provider: HoldoutSelectionEvidenceProvider | None = None,
        clock: Callable[[], datetime] | None = None,
        checkpoint_available: Callable[[str], bool] | None = None,
        checkpoint_resumable: Callable[[str], bool] | None = None,
    ) -> None:
        self._store = store
        self._authority = LeaseAuthority(
            store,
            owner_token=owner_token,
            lease_duration=lease_duration,
            clock=clock,
        )
        self._holdout = HoldoutCoordinatorAuthority(
            store=store,
            first_attempt_factory=first_attempt_factory,
            selection_evidence_provider=selection_evidence_provider,
            authority=self._authority,
        )
        self._recovery = ExperimentRecoveryOrchestrator(
            store=store,
            attempt_factory=first_attempt_factory,
            checkpoint_available=checkpoint_available or (lambda _run_id: False),
            checkpoint_resumable=checkpoint_resumable or (lambda _run_id: False),
            run_id_factory=deterministic_backtest_run_id,
        )

    def tick(self, *, occurred_at: datetime) -> SchedulerTickResult:
        """Acquire the queue head and dispatch at most DB-derived capacity."""
        _require_utc_event_time(occurred_at)
        self._authority.ensure_usable()
        while True:
            if not self._authority.has_lease:
                unowned = self._acquire_queue_head()
                if unowned is not None:
                    return unowned
            result = self._authority.execute(
                lambda lease, now_epoch_us: self._tick_owned(
                    lease,
                    now_epoch_us,
                    occurred_at,
                )
            )
            if result is not None:
                return result
            self._authority.release()

    def renew_lease(self, *, occurred_at: datetime | None = None) -> SchedulerLease:
        """Renew from the authority clock; retain worker-call compatibility."""
        if occurred_at is not None:
            _require_utc_event_time(occurred_at)
        return self._authority.renew()

    def pause(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Persist pause intent before any child notification occurs."""
        _require_utc_event_time(occurred_at)
        return run_unfenced_scheduler_operation(
            lambda: self._recovery.pause(
                experiment_id=experiment_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
            )
        )

    def cancel(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Persist cancellation intent before any child notification occurs."""
        _require_utc_event_time(occurred_at)
        return run_unfenced_scheduler_operation(
            lambda: self._recovery.cancel(
                experiment_id=experiment_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
            )
        )

    def resume(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Persist RUN intent without constructing a successor attempt early."""
        _require_utc_event_time(occurred_at)
        return run_unfenced_scheduler_operation(
            lambda: self._recovery.resume(
                experiment_id=experiment_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
            )
        )

    def retry_fold(
        self,
        *,
        experiment_id: str,
        candidate_id: str,
        fold_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Requeue one eligible terminal fold under the current scheduler fence."""
        _require_utc_event_time(occurred_at)
        return self._authority.execute_operator(
            lambda lease, now_epoch_us: self._recovery.retry_fold(
                experiment_id=experiment_id,
                candidate_id=candidate_id,
                fold_id=fold_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                lease=lease,
                now_epoch_us=now_epoch_us(),
            )
        )

    def claim_holdout_candidate(
        self,
        request: ClaimHoldoutCandidateRequest,
    ) -> HoldoutClaimReceipt:
        """Commit or exactly replay the sole candidate allowed into holdout."""
        return self._holdout.claim_candidate(request)

    def poll_execution_directive(
        self,
        attempt_id: AttemptId,
        *,
        occurred_at: datetime,
    ) -> ResearchExecutionDirective:
        """Read the exact durable RUN, PAUSE, or CANCEL intent under the fence."""
        _require_utc_event_time(occurred_at)
        return self._authority.execute(
            lambda lease, _now: self._recovery.poll_directive(
                self._load_snapshot(lease.experiment_id),
                attempt_id,
                lease,
            )
        )

    def record_checkpoint(
        self,
        attempt_id: AttemptId,
        checkpoint_ref: CheckpointRef,
        *,
        occurred_at: datetime,
    ) -> AttemptView:
        """Index an already-written strategy checkpoint under the current fence."""
        _require_utc_event_time(occurred_at)
        return self._authority.execute(
            lambda lease, now_epoch_us: self._recovery.record_checkpoint(
                self._load_snapshot(lease.experiment_id),
                attempt_id,
                checkpoint_ref,
                lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
        )

    def cooperative_stop_attempt(
        self,
        attempt_id: AttemptId,
        directive: ResearchExecutionDirective,
        *,
        occurred_at: datetime,
    ) -> ExperimentSchedulerSnapshot:
        """Fence one normal child stop and drain its durable control request."""
        _require_utc_event_time(occurred_at)
        return self._authority.execute(
            lambda lease, now_epoch_us: self._recovery.cooperative_stop(
                self._load_snapshot(lease.experiment_id),
                attempt_id,
                directive,
                lease,
                now_epoch_us=now_epoch_us,
                occurred_at=occurred_at,
            )
        )

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
            self._recovery.validate_attempt_lineage(snapshot)
            fold = self._recovery.find_fold(snapshot, attempt.spec.fold_key)
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
            fold = self._recovery.require_owned_fold(snapshot, attempt, lease)
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
    ) -> SchedulerTickResult | None:
        snapshot = self._load_snapshot(lease.experiment_id)
        _snapshot_rules.validate_worker_limit(snapshot)
        self._recovery.validate_attempt_lineage(snapshot)
        if snapshot.projection.record.status is ExperimentStatus.QUEUED:
            self._store.transition_to_running(
                snapshot.projection,
                lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
            snapshot = self._load_snapshot(lease.experiment_id)
        status = snapshot.projection.record.status
        if status in _TERMINAL_EXPERIMENT:
            return None
        if status in {
            ExperimentStatus.PAUSE_REQUESTED,
            ExperimentStatus.CANCEL_REQUESTED,
        }:
            drain = (
                self._recovery.drain_pause
                if status is ExperimentStatus.PAUSE_REQUESTED
                else self._recovery.drain_cancel
            )
            snapshot = drain(
                snapshot,
                lease,
                now_epoch_us=now_epoch_us,
                occurred_at=occurred_at,
            )
            return _result(SchedulerTickState.WAITING, snapshot, ())
        if status is not ExperimentStatus.RUNNING:
            return _result(SchedulerTickState.WAITING, snapshot, ())
        snapshot = self._recovery.recover_running(
            snapshot,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )
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
            raise _scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "durable_recovery_incomplete",
            )
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
            if stage is ExperimentStage.HOLDOUT and snapshot.holdout_claim is None:
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
        selected_holdout_ids = selected_holdout_fold_ids(snapshot)
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
                and (
                    selected_holdout_ids is None
                    or str(fold.spec.key.fold_id) in selected_holdout_ids
                )
            ),
            key=lambda fold: (
                candidate_ordinals[fold.spec.key.candidate_id],
                fold.spec.ordinal,
                str(fold.spec.key.fold_id),
            ),
        )
        dispatches: list[ExperimentDispatch] = []
        for fold in claimable[: progress.available_capacity]:
            claimed_fold, attempt = self._recovery.claim_attempt(
                snapshot,
                fold,
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
        attempt = self._recovery.find_attempt(snapshot, attempt_id)
        self._recovery.validate_attempt_lineage(snapshot)
        fold = self._recovery.find_fold(snapshot, attempt.spec.fold_key)
        if attempt.projection.status is target_status:
            if attempt.projection.failure_code is not failure_code:
                raise _scheduler_error(
                    "SPEC_INVALID",
                    "attempt_terminal_replay_mismatch",
                )
            if fold.projection.status is target_status:
                return _progress(snapshot)
            self._recovery.require_owned_fold(snapshot, attempt, lease)
            updated_attempt = attempt
        else:
            self._recovery.require_owned_fold(snapshot, attempt, lease)
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
        fold = self._recovery.find_fold(snapshot, updated_attempt.spec.fold_key)
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
        validate_holdout_snapshot(snapshot)
        return snapshot
