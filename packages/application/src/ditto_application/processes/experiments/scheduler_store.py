"""Typed durable scheduler facade over the approved Task 7 persistence ports."""
# ruff: noqa: D101, D102, D105

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateId,
    CheckpointRef,
    ContentHash,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentReaderProtocol,
    ExperimentStage,
    ExperimentStatus,
    ExperimentWriterProtocol,
    FoldId,
    FoldKey,
    FoldView,
    HoldoutClaimAuthorityCommand,
    HoldoutSelectionReason,
    SchedulerLease,
    SchedulerSlot,
    StatusEventRecord,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._holdout_contract import (
    HoldoutClaimPersistenceRequest,
    PersistedHoldoutClaim,
    persisted_holdout_claim,
    persisted_holdout_history,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments._scheduler_control import (
    ExperimentExecutionControlChanged,
    ResearchExecutionDirective,
)
from ditto_application.processes.experiments._scheduler_mutations import (
    ExperimentMutationStoreMixin,
)
from ditto_application.processes.experiments._scheduler_reasons import (
    attempt_reason,
    fold_reason,
)

__all__ = [
    "AttemptId",
    "AttemptView",
    "BacktestRunId",
    "CandidateId",
    "CheckpointRef",
    "ContentHash",
    "ExperimentDesiredState",
    "ExperimentExecutionControlChanged",
    "ExperimentFailureCode",
    "ExperimentId",
    "ExperimentProjection",
    "ExperimentSchedulerSnapshot",
    "ExperimentSchedulerStore",
    "ExperimentSchedulerStoreProtocol",
    "ExperimentStage",
    "ExperimentStatus",
    "FirstAttempt",
    "FirstAttemptFactory",
    "FoldId",
    "FoldKey",
    "FoldView",
    "QueuedAttempt",
    "ResearchExecutionDirective",
    "SchedulerLease",
]


@dataclass(frozen=True, slots=True)
class QueuedAttempt:
    """Execution-owned immutable attempt identity prepared before a fold claim."""

    spec: AttemptPersistenceSpec
    projection: AttemptProjection

    def __post_init__(self) -> None:
        if (
            type(cast("object", self.spec)) is not AttemptPersistenceSpec
            or type(cast("object", self.projection)) is not AttemptProjection
            or self.spec.attempt_id != self.projection.attempt_id
            or type(self.spec.ordinal) is not int
            or self.spec.ordinal <= 0
            or (self.spec.ordinal == 1) != (self.spec.parent_attempt_id is None)
            or (self.spec.ordinal == 1 and self.spec.resume_from_run_id is not None)
            or self.projection.status is not ExperimentStatus.QUEUED
            or self.projection.backtest_run_id is not None
            or self.projection.checkpoint_ref is not None
            or self.projection.failure_code is not None
            or self.projection.revision != 0
            or self.spec.created_at != self.projection.created_at
            or self.projection.updated_at != self.projection.created_at
        ):
            raise experiment_process_error("queued_attempt_contract_invalid")


@dataclass(frozen=True, slots=True)
class FirstAttempt(QueuedAttempt):
    def __post_init__(self) -> None:
        try:
            QueuedAttempt.__post_init__(self)
        except AppProcessError as exc:
            raise experiment_process_error("first_attempt_contract_invalid") from exc
        if (
            self.spec.ordinal != 1
            or self.spec.parent_attempt_id is not None
            or self.spec.resume_from_run_id is not None
        ):
            raise experiment_process_error("first_attempt_contract_invalid")


class FirstAttemptFactory(Protocol):
    """Build the execution-owned fingerprint and immutable first attempt."""

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt: ...

    def create_successor(
        self,
        fold: FoldView,
        parent: AttemptView,
        *,
        resume_from_run_id: BacktestRunId | None,
        occurred_at: datetime,
    ) -> QueuedAttempt: ...


@dataclass(frozen=True, slots=True)
class ExperimentSchedulerSnapshot:
    """One DB-derived scheduler view with no in-memory progress inference."""

    projection: ExperimentProjection
    launch_spec: ExperimentLaunchSpec
    folds: tuple[FoldView, ...]
    attempts: tuple[AttemptView, ...]
    holdout_claim: PersistedHoldoutClaim | None = None

    def __post_init__(self) -> None:
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
        claim = self.holdout_claim
        if claim is not None and claim.experiment_id != str(experiment_id):
            raise experiment_process_error("scheduler_snapshot_holdout_lineage_invalid")


class ExperimentSchedulerStoreProtocol(Protocol):
    def list_experiments(self) -> tuple[ExperimentProjection, ...]: ...

    def get_launch_spec(
        self,
        experiment_id: ExperimentId,
    ) -> ExperimentLaunchSpec | None: ...

    def list_experiment_artifacts(
        self,
        experiment_id: ExperimentId,
    ) -> tuple[ArtifactRecord, ...]: ...

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

    def handoff_lease(
        self, lease: SchedulerLease, *, now_epoch_us: int
    ) -> SchedulerSlot: ...

    def release_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
    ) -> SchedulerSlot: ...

    def load_snapshot(
        self, experiment_id: ExperimentId
    ) -> ExperimentSchedulerSnapshot: ...

    def list_status_events(
        self, experiment_id: ExperimentId
    ) -> tuple[StatusEventRecord, ...]: ...

    def claim_holdout_candidate(
        self,
        request: HoldoutClaimPersistenceRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> PersistedHoldoutClaim: ...

    def record_candidate_selection(
        self,
        experiment_id: ExperimentId,
        candidate_id: CandidateId,
        *,
        expected_revision: int,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object],
    ) -> ExperimentProjection: ...

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

    def claim_attempt(
        self,
        fold: FoldView,
        attempt: QueuedAttempt,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]: ...

    def transition_operator_experiment(
        self,
        projection: ExperimentProjection,
        *,
        target_status: ExperimentStatus,
        target_desired_state: ExperimentDesiredState,
        expected_revision: int,
        occurred_at: datetime,
        reason_code: str,
        detail: Mapping[str, object] | None = None,
    ) -> ExperimentProjection: ...

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
    ) -> ExperimentProjection: ...

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

    def checkpoint_attempt(
        self,
        attempt: AttemptView,
        checkpoint_ref: CheckpointRef,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> AttemptView: ...

    def cancel_attempt(
        self,
        attempt: AttemptView,
        *,
        backtest_run_id: BacktestRunId,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str,
    ) -> AttemptView: ...

    def transition_fold(
        self,
        fold: FoldView,
        *,
        target_status: ExperimentStatus,
        failure_code: ExperimentFailureCode | None,
        reason_code: str | None = None,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> FoldView: ...

    def requeue_fold_for_pause(
        self,
        fold: FoldView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> FoldView: ...

    def recover_interrupted_fold(
        self,
        fold: FoldView,
        attempt: AttemptView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]: ...

    def retry_terminal_fold(
        self,
        fold: FoldView,
        parent_attempt: AttemptView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object] | None = None,
    ) -> FoldView: ...


class ExperimentSchedulerStore(ExperimentMutationStoreMixin):
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

    def handoff_lease(
        self, lease: SchedulerLease, *, now_epoch_us: int
    ) -> SchedulerSlot:
        return self._writer.handoff_lease(lease.fence, now_epoch_us=now_epoch_us)

    def release_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
    ) -> SchedulerSlot:
        return self._writer.release_lease(
            lease.fence,
            now_epoch_us=now_epoch_us,
        )

    def load_snapshot(self, experiment_id: ExperimentId) -> ExperimentSchedulerSnapshot:
        projection = self._reader.get_experiment_projection(experiment_id)
        launch_spec = self._reader.get_launch_spec(experiment_id)
        if projection is None or launch_spec is None:
            raise experiment_process_error("scheduler_experiment_not_found")
        folds = self._reader.list_folds(experiment_id)
        attempts = self._reader.list_experiment_attempts(experiment_id)
        claim = self._reader.get_holdout_claim_for_experiment(experiment_id)
        holdout_claim = persisted_holdout_history(
            claim,
            () if claim is None else self._reader.list_status_events(experiment_id),
        )
        return ExperimentSchedulerSnapshot(
            projection=projection,
            launch_spec=launch_spec,
            folds=folds,
            attempts=attempts,
            holdout_claim=holdout_claim,
        )

    def claim_holdout_candidate(
        self,
        request: HoldoutClaimPersistenceRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> PersistedHoldoutClaim:
        receipt = self._writer.claim_holdout_candidate(
            HoldoutClaimAuthorityCommand(
                experiment_id=ExperimentId(request.experiment_id),
                candidate_id=CandidateId(request.candidate_id),
                expected_revision=request.expected_revision,
                expected_selection_evidence_hash=ContentHash(
                    request.expected_selection_evidence_hash
                ),
                operator_confirmation=request.operator_confirmation,
                selection_reason=HoldoutSelectionReason(
                    request.selection_reason_code,
                    request.selection_reason_summary,
                ),
                resolved_reproduction_fingerprint=(
                    None
                    if request.resolved_reproduction_fingerprint is None
                    else ContentHash(request.resolved_reproduction_fingerprint)
                ),
                occurred_at=request.occurred_at,
                event_detail_extension=request.event_detail_extension,
            ),
            lease_fence=None if lease is None else lease.fence,
            now_epoch_us=now_epoch_us,
        )
        return persisted_holdout_claim(
            receipt.claim,
            experiment_revision=receipt.experiment_revision,
            event_id=receipt.event_id,
        )

    def transition_to_running(
        self,
        projection: ExperimentProjection,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> ExperimentProjection:
        target_stage = (
            ExperimentStage.EXPLORATION
            if projection.record.stage is ExperimentStage.PREFLIGHT
            else projection.record.stage
        )
        return self._writer.transition_scheduled_experiment(
            projection.record.experiment_id,
            target_status=ExperimentStatus.RUNNING,
            target_stage=target_stage,
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
        attempt: QueuedAttempt,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]:
        if attempt.spec.fold_key != fold.spec.key:
            raise experiment_process_error("attempt_fold_lineage_mismatch")
        fold_projection, attempt_projection = self._writer.claim_fold_and_add_attempt(
            fold.spec.key,
            attempt.spec,
            attempt.projection,
            expected_fold_revision=fold.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
        )
        return (
            FoldView(fold.spec, fold_projection),
            AttemptView(attempt.spec, attempt_projection),
        )

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
        return self._writer.transition_scheduled_experiment(
            projection.record.experiment_id,
            target_status=target_status,
            target_stage=projection.record.stage,
            failure_code=None,
            expected_revision=projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            attempt_started=attempt_started,
            precondition_repairable=False,
            reason_code=reason_code,
            detail={},
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
        if target_status is ExperimentStatus.RUNNING:
            self._raise_if_execution_control_changed(attempt)
        try:
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
                reason_code=attempt_reason(target_status, failure_code),
                detail={},
            )
        except AnalysisError:
            if target_status is ExperimentStatus.RUNNING:
                self._raise_if_execution_control_changed(attempt)
            raise
        return AttemptView(attempt.spec, projection)

    def _raise_if_execution_control_changed(self, attempt: AttemptView) -> None:
        projection = self._reader.get_experiment_projection(
            attempt.spec.fold_key.experiment_id
        )
        if (
            projection is None
            or projection.record.desired_state is ExperimentDesiredState.RUN
        ):
            return
        raise ExperimentExecutionControlChanged(
            "experiment execution control changed before attempt start",
            details={
                "code": "CONTROL_CHANGED",
                "reason": "execution_control_changed_before_start",
                "desired_state": projection.record.desired_state.value,
            },
        )

    def checkpoint_attempt(
        self,
        attempt: AttemptView,
        checkpoint_ref: CheckpointRef,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> AttemptView:
        projection = self._writer.transition_attempt(
            attempt.spec.attempt_id,
            target_status=ExperimentStatus.RUNNING,
            backtest_run_id=attempt.projection.backtest_run_id,
            checkpoint_ref=checkpoint_ref,
            failure_code=None,
            expected_revision=attempt.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            reason_code="strategy_run_checkpoint_indexed",
            detail={"checkpoint_ref": str(checkpoint_ref)},
        )
        return AttemptView(attempt.spec, projection)

    def cancel_attempt(
        self,
        attempt: AttemptView,
        *,
        backtest_run_id: BacktestRunId,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str,
    ) -> AttemptView:
        projection = self._writer.transition_attempt(
            attempt.spec.attempt_id,
            target_status=ExperimentStatus.CANCELLED,
            backtest_run_id=backtest_run_id,
            checkpoint_ref=attempt.projection.checkpoint_ref,
            failure_code=None,
            expected_revision=attempt.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            reason_code=reason_code,
            detail={},
        )
        return AttemptView(attempt.spec, projection)

    def transition_fold(
        self,
        fold: FoldView,
        *,
        target_status: ExperimentStatus,
        failure_code: ExperimentFailureCode | None,
        reason_code: str | None = None,
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
            reason_code=reason_code or fold_reason(target_status, failure_code),
            detail={},
        )
        return FoldView(fold.spec, projection)

    def requeue_fold_for_pause(
        self,
        fold: FoldView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> FoldView:
        projection = self._writer.requeue_fold_for_pause(
            fold.spec.key,
            expected_fold_revision=fold.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            detail={},
        )
        return FoldView(fold.spec, projection)

    def recover_interrupted_fold(
        self,
        fold: FoldView,
        attempt: AttemptView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldView, AttemptView]:
        fold_projection, attempt_projection = self._writer.requeue_interrupted_fold(
            fold.spec.key,
            attempt.spec.attempt_id,
            expected_fold_revision=fold.projection.revision,
            expected_attempt_revision=attempt.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            detail={"reclaimed_by": lease.owner_token},
        )
        return (
            FoldView(fold.spec, fold_projection),
            AttemptView(attempt.spec, attempt_projection),
        )
