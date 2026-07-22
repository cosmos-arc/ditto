"""Typed durable scheduler facade over the approved Task 7 persistence ports."""

# These methods preserve explicit revisions, fences, and event timestamps.
# ruff: noqa: D102

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from ditto_analysis.experiments import (
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentReaderProtocol,
    ExperimentStage,
    ExperimentStatus,
    ExperimentWriterProtocol,
    FoldView,
    SchedulerLease,
    SchedulerSlot,
)

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)

__all__ = [
    "ExperimentSchedulerSnapshot",
    "ExperimentSchedulerStore",
    "ExperimentSchedulerStoreProtocol",
    "FirstAttempt",
    "FirstAttemptFactory",
]


@dataclass(frozen=True, slots=True)
class FirstAttempt:
    """Execution-owned first-attempt identity prepared before durable claim."""

    spec: AttemptPersistenceSpec
    projection: AttemptProjection

    def __post_init__(self) -> None:
        """Require one exact, initially queued, non-resume attempt pair."""
        if (
            type(cast("object", self.spec)) is not AttemptPersistenceSpec
            or type(cast("object", self.projection)) is not AttemptProjection
            or self.spec.attempt_id != self.projection.attempt_id
            or self.spec.ordinal != 1
            or self.spec.parent_attempt_id is not None
            or self.spec.resume_from_run_id is not None
            or self.projection.status is not ExperimentStatus.QUEUED
            or self.projection.backtest_run_id is not None
            or self.projection.checkpoint_ref is not None
            or self.projection.failure_code is not None
            or self.projection.revision != 0
            or self.spec.created_at != self.projection.created_at
            or self.projection.updated_at != self.projection.created_at
        ):
            raise experiment_process_error("first_attempt_contract_invalid")


class FirstAttemptFactory(Protocol):
    """Build the execution-owned fingerprint and immutable first attempt."""

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt: ...


@dataclass(frozen=True, slots=True)
class ExperimentSchedulerSnapshot:
    """One DB-derived scheduler view with no in-memory progress inference."""

    projection: ExperimentProjection
    launch_spec: ExperimentLaunchSpec
    folds: tuple[FoldView, ...]
    attempts: tuple[AttemptView, ...]

    def __post_init__(self) -> None:
        """Require one lineage-complete experiment snapshot."""
        experiment_id = self.projection.record.experiment_id
        if self.launch_spec.experiment_id != experiment_id:
            raise experiment_process_error("scheduler_snapshot_launch_mismatch")
        candidate_ids = frozenset(
            candidate.candidate_id for candidate in self.launch_spec.candidates
        )
        fold_keys = tuple(fold.spec.key for fold in self.folds)
        if len(set(fold_keys)) != len(fold_keys) or any(
            fold.spec.key != fold.projection.key
            or fold.spec.key.experiment_id != experiment_id
            or fold.spec.key.candidate_id not in candidate_ids
            for fold in self.folds
        ):
            raise experiment_process_error("scheduler_snapshot_fold_lineage_invalid")
        attempt_ids = tuple(attempt.spec.attempt_id for attempt in self.attempts)
        if len(set(attempt_ids)) != len(attempt_ids) or any(
            attempt.spec.attempt_id != attempt.projection.attempt_id
            or attempt.spec.fold_key not in fold_keys
            for attempt in self.attempts
        ):
            raise experiment_process_error("scheduler_snapshot_attempt_lineage_invalid")


class ExperimentSchedulerStoreProtocol(Protocol):
    """Narrow Task 9 scheduling operations over the Task 7 store contracts."""

    def list_dispatchable_experiments(self) -> tuple[ExperimentProjection, ...]: ...

    def get_scheduler_slot(self) -> SchedulerSlot: ...

    def try_claim_lease(
        self,
        experiment_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
        lease_until_epoch_us: int,
    ) -> SchedulerLease | None: ...

    def renew_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        new_lease_until_epoch_us: int,
    ) -> SchedulerLease: ...

    def load_snapshot(
        self, experiment_id: ExperimentId
    ) -> ExperimentSchedulerSnapshot: ...

    def transition_to_running(
        self,
        projection: ExperimentProjection,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> ExperimentProjection: ...

    def advance_stage(
        self,
        projection: ExperimentProjection,
        target_stage: ExperimentStage,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> ExperimentProjection: ...

    def claim_first_attempt(
        self,
        fold: FoldView,
        first_attempt: FirstAttempt,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]: ...

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
    ) -> AttemptView: ...

    def transition_fold(
        self,
        fold: FoldView,
        *,
        target_status: ExperimentStatus,
        failure_code: ExperimentFailureCode | None,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> FoldView: ...


class ExperimentSchedulerStore:
    """Adapt the exact Task 7 reader/writer protocols to scheduler intents."""

    def __init__(
        self,
        reader: ExperimentReaderProtocol,
        writer: ExperimentWriterProtocol,
    ) -> None:
        self._reader = reader
        self._writer = writer

    def list_dispatchable_experiments(self) -> tuple[ExperimentProjection, ...]:
        return self._reader.list_dispatchable_experiments()

    def get_scheduler_slot(self) -> SchedulerSlot:
        return self._reader.get_scheduler_slot()

    def try_claim_lease(
        self,
        experiment_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
        lease_until_epoch_us: int,
    ) -> SchedulerLease | None:
        return self._writer.try_claim_lease(
            experiment_id,
            owner_token,
            expected_revision=expected_revision,
            now_epoch_us=now_epoch_us,
            lease_until_epoch_us=lease_until_epoch_us,
        )

    def renew_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        new_lease_until_epoch_us: int,
    ) -> SchedulerLease:
        return self._writer.renew_lease(
            lease.fence,
            now_epoch_us=now_epoch_us,
            new_lease_until_epoch_us=new_lease_until_epoch_us,
        )

    def load_snapshot(self, experiment_id: ExperimentId) -> ExperimentSchedulerSnapshot:
        projection = self._reader.get_experiment_projection(experiment_id)
        launch_spec = self._reader.get_launch_spec(experiment_id)
        if projection is None or launch_spec is None:
            raise experiment_process_error("scheduler_experiment_not_found")
        folds = self._reader.list_folds(experiment_id)
        attempts = self._reader.list_experiment_attempts(experiment_id)
        return ExperimentSchedulerSnapshot(
            projection=projection,
            launch_spec=launch_spec,
            folds=folds,
            attempts=attempts,
        )

    def transition_to_running(
        self,
        projection: ExperimentProjection,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> ExperimentProjection:
        return self._writer.transition_scheduled_experiment(
            projection.record.experiment_id,
            target_status=ExperimentStatus.RUNNING,
            target_stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            expected_revision=projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="scheduler_dispatch",
            detail={},
        )

    def advance_stage(
        self,
        projection: ExperimentProjection,
        target_stage: ExperimentStage,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> ExperimentProjection:
        return self._writer.advance_experiment_stage(
            projection.record.experiment_id,
            target_stage=target_stage,
            expected_revision=projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            reason_code="scheduler_stage_complete",
            detail={"completed_stage": projection.record.stage.value},
        )

    def claim_first_attempt(
        self,
        fold: FoldView,
        first_attempt: FirstAttempt,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]:
        if first_attempt.spec.fold_key != fold.spec.key:
            raise experiment_process_error("first_attempt_fold_lineage_mismatch")
        fold_projection, attempt_projection = self._writer.claim_fold_and_add_attempt(
            fold.spec.key,
            first_attempt.spec,
            first_attempt.projection,
            expected_fold_revision=fold.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )
        return (
            FoldView(fold.spec, fold_projection),
            AttemptView(first_attempt.spec, attempt_projection),
        )

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
        projection = self._writer.transition_attempt(
            attempt.spec.attempt_id,
            target_status=target_status,
            backtest_run_id=backtest_run_id,
            checkpoint_ref=attempt.projection.checkpoint_ref,
            failure_code=failure_code,
            expected_revision=attempt.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            reason_code=_attempt_reason(target_status, failure_code),
            detail={},
        )
        return AttemptView(attempt.spec, projection)

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
        projection = self._writer.transition_fold(
            fold.spec.key,
            target_status=target_status,
            claim_owner_token=None,
            failure_code=failure_code,
            expected_revision=fold.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            reason_code=_fold_reason(target_status, failure_code),
            detail={},
        )
        return FoldView(fold.spec, projection)


def _attempt_reason(
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
) -> str:
    if status is ExperimentStatus.RUNNING:
        return "first_attempt_started"
    if status is ExperimentStatus.COMPLETED:
        return "first_attempt_completed"
    if failure_code is ExperimentFailureCode.CANDIDATE_FAILED:
        return "candidate_attempt_failed"
    return "system_attempt_failed"


def _fold_reason(
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
) -> str:
    if status is ExperimentStatus.COMPLETED:
        return "fold_completed"
    if status is ExperimentStatus.CANCELLED:
        return "candidate_isolated_after_failure"
    if failure_code is ExperimentFailureCode.CANDIDATE_FAILED:
        return "candidate_fold_failed"
    return "system_fold_failed"
