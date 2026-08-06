"""Durable pause, cancel, successor, and lease-recovery orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime

from ditto_application.mutation_idempotency import MutationIdempotency
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
    RetryFoldControlRequest,
)
from ditto_application.processes.experiments._coordinator_snapshot import (
    scheduler_error,
)
from ditto_application.processes.experiments._mutation_receipts import (
    OperatorControlIntent,
    RetryFoldRequestContext,
    control_receipt_detail,
    persist_operator_control,
    replay_control_receipt,
)
from ditto_application.processes.experiments.scheduler_store import (
    AttemptId,
    AttemptView,
    BacktestRunId,
    CandidateId,
    CheckpointRef,
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentProjection,
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStoreProtocol,
    ExperimentStatus,
    FirstAttempt,
    FirstAttemptFactory,
    FoldId,
    FoldKey,
    FoldView,
    ResearchExecutionDirective,
    SchedulerLease,
)

__all__ = ["ExperimentRecoveryOrchestrator"]

_LIVE = frozenset({ExperimentStatus.QUEUED, ExperimentStatus.RUNNING})
_ATTEMPT_TERMINAL = frozenset(
    {
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
    }
)


class ExperimentRecoveryOrchestrator:
    """Apply Task 10 control semantics through the approved scheduler facade."""

    def __init__(
        self,
        *,
        store: ExperimentSchedulerStoreProtocol,
        attempt_factory: FirstAttemptFactory,
        checkpoint_available: Callable[[str], bool],
        checkpoint_resumable: Callable[[str], bool],
        run_id_factory: Callable[[AttemptId, ContentHash], BacktestRunId],
        retryable_stage_roles: Mapping[object, object],
    ) -> None:
        self._store = store
        self._attempt_factory = attempt_factory
        self._checkpoint_available = checkpoint_available
        self._checkpoint_resumable = checkpoint_resumable
        self._run_id_factory = run_id_factory
        self._retryable_stage_roles = retryable_stage_roles

    def pause(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt:
        return persist_operator_control(
            self._store,
            idempotency,
            experiment_id=experiment_id,
            intent=OperatorControlIntent(
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                target_status=ExperimentStatus.PAUSE_REQUESTED,
                target_desired_state=ExperimentDesiredState.PAUSE,
                reason_code="operator_pause",
            ),
        )

    def cancel(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt:
        return persist_operator_control(
            self._store,
            idempotency,
            experiment_id=experiment_id,
            intent=OperatorControlIntent(
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                target_status=ExperimentStatus.CANCEL_REQUESTED,
                target_desired_state=ExperimentDesiredState.CANCEL,
                reason_code="operator_cancel",
            ),
        )

    def resume(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt:
        return persist_operator_control(
            self._store,
            idempotency,
            experiment_id=experiment_id,
            intent=OperatorControlIntent(
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                target_status=ExperimentStatus.QUEUED,
                target_desired_state=ExperimentDesiredState.RUN,
                reason_code="operator_resume",
            ),
        )

    def retry_fold(
        self,
        request: RetryFoldControlRequest,
        *,
        lease: SchedulerLease,
        now_epoch_us: int,
    ) -> ExperimentControlReceipt:
        replay = replay_control_receipt(
            self._store,
            request.idempotency,
            experiment_id=request.experiment_id,
            candidate_id=request.candidate_id,
            fold_id=request.fold_id,
        )
        if replay is not None:
            return replay
        snapshot = self._store.load_snapshot(ExperimentId(request.experiment_id))
        self.validate_attempt_lineage(snapshot)
        key = FoldKey(
            ExperimentId(request.experiment_id),
            CandidateId(request.candidate_id),
            FoldId(request.fold_id),
        )
        fold = _find_fold(snapshot, key)
        retryable_role = self._retryable_stage_roles.get(
            snapshot.projection.record.stage,
        )
        if fold.spec.fold_role is not retryable_role:
            raise scheduler_error(
                "SPEC_INVALID",
                "terminal_fold_retry_stage_closed",
            )
        if fold.projection.revision != request.expected_revision:
            raise scheduler_error("SPEC_INVALID", "stale_fold_revision")
        if fold.projection.status is not ExperimentStatus.FAILED:
            raise scheduler_error(
                "SPEC_INVALID",
                "terminal_fold_retry_requires_failed_fold",
            )
        parent = _latest_attempt(snapshot, key)
        expected_receipt = _receipt(snapshot.projection, request.occurred_at, ())
        detail = (
            {}
            if request.idempotency is None
            else control_receipt_detail(
                request.idempotency,
                expected_receipt,
                request_context=RetryFoldRequestContext(
                    candidate_id=request.candidate_id,
                    fold_id=request.fold_id,
                    expected_revision=request.expected_revision,
                ),
            )
        )
        try:
            self._store.retry_terminal_fold(
                fold,
                parent,
                lease,
                now_epoch_us=now_epoch_us,
                occurred_at=request.occurred_at,
                detail=detail,
            )
        except Exception:
            replay = replay_control_receipt(
                self._store,
                request.idempotency,
                experiment_id=request.experiment_id,
                candidate_id=request.candidate_id,
                fold_id=request.fold_id,
            )
            if replay is not None:
                return replay
            raise
        if request.idempotency is not None:
            persisted = replay_control_receipt(
                self._store,
                request.idempotency,
                experiment_id=request.experiment_id,
                candidate_id=request.candidate_id,
                fold_id=request.fold_id,
            )
            if persisted is None:
                raise scheduler_error(
                    "IDEMPOTENCY_RECEIPT_INVALID",
                    "idempotency_receipt_invalid",
                )
            return replace(persisted, replayed=False)
        projection = self._store.load_snapshot(key.experiment_id).projection
        return _receipt(projection, request.occurred_at, ())

    def poll_directive(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        attempt_id: AttemptId,
        lease: SchedulerLease,
    ) -> ResearchExecutionDirective:
        attempt = _find_attempt(snapshot, attempt_id)
        fold = _find_fold(snapshot, attempt.spec.fold_key)
        if attempt.projection.status in _LIVE and (
            fold.projection.status is not ExperimentStatus.RUNNING
            or fold.projection.claim_owner_token != lease.owner_token
        ):
            raise scheduler_error("LEASE_LOST", "attempt_fold_not_owned_by_lease")
        desired = snapshot.projection.record.desired_state
        return ResearchExecutionDirective(desired.value)

    def record_checkpoint(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        attempt_id: AttemptId,
        checkpoint_ref: CheckpointRef,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> AttemptView:
        attempt = _find_attempt(snapshot, attempt_id)
        run_id = attempt.projection.backtest_run_id
        if (
            run_id is None
            or str(checkpoint_ref) != str(run_id)
            or not self._checkpoint_available(str(run_id))
        ):
            raise scheduler_error("SPEC_INVALID", "checkpoint_reference_unverified")
        if attempt.projection.checkpoint_ref == checkpoint_ref:
            return attempt
        if attempt.projection.status is not ExperimentStatus.RUNNING:
            raise scheduler_error("SPEC_INVALID", "checkpoint_reference_unverified")
        return self._store.checkpoint_attempt(
            attempt,
            checkpoint_ref,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )

    def cooperative_stop(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        attempt_id: AttemptId,
        directive: ResearchExecutionDirective,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> ExperimentSchedulerSnapshot:
        durable = ResearchExecutionDirective(
            snapshot.projection.record.desired_state.value
        )
        if directive is ResearchExecutionDirective.RUN or directive is not durable:
            raise scheduler_error("SPEC_INVALID", "cooperative_stop_intent_drift")
        attempt = _find_attempt(snapshot, attempt_id)
        fold = _find_fold(snapshot, attempt.spec.fold_key)
        run_id = attempt.projection.backtest_run_id or self._run_id_factory(
            attempt.spec.attempt_id,
            attempt.spec.reproduction_fingerprint,
        )
        if attempt.projection.status in _LIVE:
            self._store.cancel_attempt(
                attempt,
                backtest_run_id=run_id,
                lease=lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
                reason_code=(
                    "pause_attempt_drained"
                    if directive is ResearchExecutionDirective.PAUSE
                    else "cancel_attempt_drained"
                ),
            )
        snapshot = self._store.load_snapshot(lease.experiment_id)
        fold = _find_fold(snapshot, fold.spec.key)
        if directive is ResearchExecutionDirective.PAUSE:
            if fold.projection.status is ExperimentStatus.RUNNING:
                self._store.requeue_fold_for_pause(
                    fold,
                    lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                )
            return self.drain_pause(
                self._store.load_snapshot(lease.experiment_id),
                lease,
                now_epoch_us=now_epoch_us,
                occurred_at=occurred_at,
            )
        if fold.projection.status is ExperimentStatus.RUNNING:
            self._store.transition_fold(
                fold,
                target_status=ExperimentStatus.CANCELLED,
                failure_code=None,
                lease=lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
        return self.drain_cancel(
            self._store.load_snapshot(lease.experiment_id),
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )

    def recover_running(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> ExperimentSchedulerSnapshot:
        """Recover only orphaned work; current-owner work remains live."""
        for fold in snapshot.folds:
            if fold.projection.status is not ExperimentStatus.RUNNING:
                continue
            live = _live_attempts(snapshot, fold.spec.key)
            if fold.projection.claim_owner_token == lease.owner_token:
                if len(live) != 1:
                    self._repair_terminal_fold(
                        snapshot,
                        fold,
                        lease,
                        now_epoch_us=now_epoch_us,
                        occurred_at=occurred_at,
                    )
                continue
            if len(live) == 1:
                self._reconcile_live_checkpoint(
                    live[0],
                    lease,
                    now_epoch_us=now_epoch_us,
                    occurred_at=occurred_at,
                )
                refreshed = self._store.load_snapshot(lease.experiment_id)
                self._store.recover_interrupted_fold(
                    _find_fold(refreshed, fold.spec.key),
                    _find_attempt(refreshed, live[0].spec.attempt_id),
                    lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                )
            elif not live:
                self._repair_terminal_fold(
                    snapshot,
                    fold,
                    lease,
                    now_epoch_us=now_epoch_us,
                    occurred_at=occurred_at,
                )
            else:
                raise scheduler_error(
                    "EXPERIMENT_INTEGRITY_FAILED",
                    "multiple_live_attempts_for_fold",
                )
            snapshot = self._store.load_snapshot(lease.experiment_id)
        return self._store.load_snapshot(lease.experiment_id)

    def drain_pause(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> ExperimentSchedulerSnapshot:
        status = snapshot.projection.record.status
        if status is ExperimentStatus.PAUSED:
            return snapshot
        if status is not ExperimentStatus.PAUSE_REQUESTED:
            raise scheduler_error("SPEC_INVALID", "pause_drain_state_invalid")
        for fold in snapshot.folds:
            if fold.projection.status is not ExperimentStatus.RUNNING:
                continue
            live = _live_attempts(snapshot, fold.spec.key)
            if len(live) > 1:
                raise scheduler_error(
                    "EXPERIMENT_INTEGRITY_FAILED",
                    "multiple_live_attempts_for_fold",
                )
            if (
                live
                and live[0].projection.status is ExperimentStatus.RUNNING
                and fold.projection.claim_owner_token == lease.owner_token
            ):
                continue
            if live and fold.projection.claim_owner_token == lease.owner_token:
                attempt = live[0]
                run_id = attempt.projection.backtest_run_id or self._run_id_factory(
                    attempt.spec.attempt_id,
                    attempt.spec.reproduction_fingerprint,
                )
                self._store.cancel_attempt(
                    attempt,
                    backtest_run_id=run_id,
                    lease=lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                    reason_code="pause_attempt_drained",
                )
                refreshed = self._store.load_snapshot(lease.experiment_id)
                self._store.requeue_fold_for_pause(
                    _find_fold(refreshed, fold.spec.key),
                    lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                )
            elif live:
                self._reconcile_live_checkpoint(
                    live[0],
                    lease,
                    now_epoch_us=now_epoch_us,
                    occurred_at=occurred_at,
                )
                refreshed = self._store.load_snapshot(lease.experiment_id)
                self._store.recover_interrupted_fold(
                    _find_fold(refreshed, fold.spec.key),
                    _find_attempt(refreshed, live[0].spec.attempt_id),
                    lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                )
            else:
                self._store.requeue_fold_for_pause(
                    fold,
                    lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                )
            snapshot = self._store.load_snapshot(lease.experiment_id)
        if not _has_live_children(snapshot):
            self._store.transition_controlled_experiment(
                snapshot.projection,
                target_status=ExperimentStatus.PAUSED,
                lease=lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
                attempt_started=bool(snapshot.attempts),
                reason_code="pause_drained",
            )
        return self._store.load_snapshot(lease.experiment_id)

    def drain_cancel(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> ExperimentSchedulerSnapshot:
        status = snapshot.projection.record.status
        if status is ExperimentStatus.CANCELLED:
            return snapshot
        if status is not ExperimentStatus.CANCEL_REQUESTED:
            raise scheduler_error("SPEC_INVALID", "cancel_drain_state_invalid")
        for fold in snapshot.folds:
            if fold.projection.status not in _LIVE:
                continue
            live = _live_attempts(snapshot, fold.spec.key)
            if (
                live
                and live[0].projection.status is ExperimentStatus.RUNNING
                and fold.projection.claim_owner_token == lease.owner_token
            ):
                continue
            for attempt in live:
                run_id = attempt.projection.backtest_run_id or self._run_id_factory(
                    attempt.spec.attempt_id,
                    attempt.spec.reproduction_fingerprint,
                )
                self._store.cancel_attempt(
                    attempt,
                    backtest_run_id=run_id,
                    lease=lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                    reason_code="cancel_attempt_drained",
                )
            refreshed = self._store.load_snapshot(lease.experiment_id)
            current = _find_fold(refreshed, fold.spec.key)
            if current.projection.status in _LIVE:
                self._store.transition_fold(
                    current,
                    target_status=ExperimentStatus.CANCELLED,
                    failure_code=None,
                    lease=lease,
                    now_epoch_us=now_epoch_us(),
                    occurred_at=occurred_at,
                    reason_code="cancel_fold_drained",
                )
            snapshot = self._store.load_snapshot(lease.experiment_id)
        if not _has_live_children(snapshot):
            self._store.transition_controlled_experiment(
                snapshot.projection,
                target_status=ExperimentStatus.CANCELLED,
                lease=lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
                attempt_started=bool(snapshot.attempts),
                reason_code="cancel_drained",
            )
        return self._store.load_snapshot(lease.experiment_id)

    def claim_attempt(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        fold: FoldView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]:
        history = _attempts_for_fold(snapshot, fold.spec.key)
        if not history:
            first = self._attempt_factory.create(fold, occurred_at)
            if type(first) is not FirstAttempt:
                raise scheduler_error("SPEC_INVALID", "first_attempt_factory_invalid")
            return self._store.claim_first_attempt(
                fold,
                first,
                lease,
                now_epoch_us=now_epoch_us,
                occurred_at=occurred_at,
            )
        parent = history[-1]
        resume_from_run_id = _nearest_resumable_run_id(
            history,
            self._checkpoint_resumable,
        )
        successor = self._attempt_factory.create_successor(
            fold,
            parent,
            resume_from_run_id=resume_from_run_id,
            occurred_at=occurred_at,
        )
        return self._store.claim_attempt(
            fold,
            successor,
            lease,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )

    @staticmethod
    def validate_attempt_lineage(snapshot: ExperimentSchedulerSnapshot) -> None:
        for fold in snapshot.folds:
            history = _attempts_for_fold(snapshot, fold.spec.key)
            for index, attempt in enumerate(history, start=1):
                projection = attempt.projection
                if projection.status is ExperimentStatus.QUEUED and (
                    projection.backtest_run_id is not None
                    or projection.checkpoint_ref is not None
                    or projection.failure_code is not None
                ):
                    raise scheduler_error(
                        "SPEC_INVALID",
                        "queued_attempt_projection_invalid",
                    )
                if projection.checkpoint_ref is not None and (
                    projection.backtest_run_id is None
                    or projection.checkpoint_ref
                    != CheckpointRef(str(projection.backtest_run_id))
                ):
                    raise scheduler_error(
                        "SPEC_INVALID",
                        "attempt_checkpoint_reference_drift",
                    )
                if attempt.spec.ordinal != index:
                    raise scheduler_error("SPEC_INVALID", "attempt_ordinal_gap")
                if index == 1:
                    if (
                        attempt.spec.parent_attempt_id is not None
                        or attempt.spec.resume_from_run_id is not None
                    ):
                        raise scheduler_error("SPEC_INVALID", "first_attempt_invalid")
                    continue
                parent = history[index - 2]
                if (
                    attempt.spec.parent_attempt_id != parent.spec.attempt_id
                    or attempt.spec.reproduction_fingerprint
                    != parent.spec.reproduction_fingerprint
                    or (
                        attempt.spec.resume_from_run_id is not None
                        and all(
                            ancestor.projection.backtest_run_id
                            != attempt.spec.resume_from_run_id
                            for ancestor in history[: index - 1]
                        )
                    )
                ):
                    raise scheduler_error("SPEC_INVALID", "attempt_lineage_drift")

    @staticmethod
    def find_attempt(
        snapshot: ExperimentSchedulerSnapshot,
        attempt_id: AttemptId,
    ) -> AttemptView:
        return _find_attempt(snapshot, attempt_id)

    @staticmethod
    def find_fold(
        snapshot: ExperimentSchedulerSnapshot,
        key: FoldKey,
    ) -> FoldView:
        return _find_fold(snapshot, key)

    @staticmethod
    def require_owned_fold(
        snapshot: ExperimentSchedulerSnapshot,
        attempt: AttemptView,
        lease: SchedulerLease,
    ) -> FoldView:
        fold = _find_fold(snapshot, attempt.spec.fold_key)
        if (
            fold.projection.status is not ExperimentStatus.RUNNING
            or fold.projection.claim_owner_token != lease.owner_token
        ):
            raise scheduler_error(
                "LEASE_LOST",
                "attempt_fold_not_owned_by_lease",
            )
        return fold

    def _reconcile_live_checkpoint(
        self,
        attempt: AttemptView,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> None:
        run_id = attempt.projection.backtest_run_id
        if (
            attempt.projection.status is ExperimentStatus.RUNNING
            and run_id is not None
            and attempt.projection.checkpoint_ref is None
            and self._checkpoint_available(str(run_id))
        ):
            self._store.checkpoint_attempt(
                attempt,
                CheckpointRef(str(run_id)),
                lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )

    def _repair_terminal_fold(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        fold: FoldView,
        lease: SchedulerLease,
        *,
        now_epoch_us: Callable[[], int],
        occurred_at: datetime,
    ) -> None:
        parent = _latest_attempt(snapshot, fold.spec.key)
        status = parent.projection.status
        if status not in _ATTEMPT_TERMINAL:
            raise scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "running_fold_without_terminal_or_live_attempt",
            )
        self._store.transition_fold(
            fold,
            target_status=status,
            failure_code=parent.projection.failure_code,
            lease=lease,
            now_epoch_us=now_epoch_us(),
            occurred_at=occurred_at,
        )


def _attempts_for_fold(
    snapshot: ExperimentSchedulerSnapshot,
    key: FoldKey,
) -> tuple[AttemptView, ...]:
    return tuple(
        sorted(
            (item for item in snapshot.attempts if item.spec.fold_key == key),
            key=lambda item: (item.spec.ordinal, str(item.spec.attempt_id)),
        )
    )


def _live_attempts(
    snapshot: ExperimentSchedulerSnapshot,
    key: FoldKey,
) -> tuple[AttemptView, ...]:
    return tuple(
        item
        for item in _attempts_for_fold(snapshot, key)
        if item.projection.status in _LIVE
    )


def _latest_attempt(
    snapshot: ExperimentSchedulerSnapshot,
    key: FoldKey,
) -> AttemptView:
    history = _attempts_for_fold(snapshot, key)
    if not history:
        raise scheduler_error("SPEC_INVALID", "fold_attempt_history_missing")
    return history[-1]


def _find_attempt(
    snapshot: ExperimentSchedulerSnapshot,
    attempt_id: AttemptId,
) -> AttemptView:
    matches = tuple(
        item for item in snapshot.attempts if item.spec.attempt_id == attempt_id
    )
    if len(matches) != 1:
        raise scheduler_error("SPEC_INVALID", "attempt_not_found_or_ambiguous")
    return matches[0]


def _find_fold(snapshot: ExperimentSchedulerSnapshot, key: FoldKey) -> FoldView:
    matches = tuple(item for item in snapshot.folds if item.spec.key == key)
    if len(matches) != 1:
        raise scheduler_error("SPEC_INVALID", "fold_not_found_or_ambiguous")
    return matches[0]


def _has_live_children(snapshot: ExperimentSchedulerSnapshot) -> bool:
    return any(item.projection.status in _LIVE for item in snapshot.attempts) or any(
        item.projection.status is ExperimentStatus.RUNNING for item in snapshot.folds
    )


def _nearest_resumable_run_id(
    history: tuple[AttemptView, ...],
    checkpoint_resumable: Callable[[str], bool],
) -> BacktestRunId | None:
    for attempt in reversed(history):
        run_id = attempt.projection.backtest_run_id
        if run_id is not None and checkpoint_resumable(str(run_id)):
            return run_id
    return None


def _receipt(
    projection: ExperimentProjection,
    occurred_at: datetime,
    live_run_ids: tuple[str, ...],
) -> ExperimentControlReceipt:
    record = projection.record
    return ExperimentControlReceipt(
        experiment_id=str(record.experiment_id),
        status=record.status.value,
        desired_state=record.desired_state.value,
        revision=projection.revision,
        occurred_at=occurred_at,
        live_run_ids=live_run_ids,
    )
