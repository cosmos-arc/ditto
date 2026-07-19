"""Typed persistence ports for experiment control-plane consumers."""

# Protocol signatures are the documentation surface; method names mirror DTO verbs.
# ruff: noqa: D102, PLR0913

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from ditto_analysis.experiments.models import (
    AttemptId,
    BacktestRunId,
    CheckpointRef,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    ExperimentProjection,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldView,
    GateEvaluationRecord,
    HoldoutClaimRecord,
    LeaseFence,
    ResearchCycleIdentity,
    SchedulerLease,
    SchedulerSlot,
    StatusEventRecord,
)
from ditto_analysis.experiments.specs import CandidateSpec, ExperimentLaunchSpec

__all__ = ["ExperimentReaderProtocol", "ExperimentWriterProtocol"]


class ExperimentReaderProtocol(Protocol):
    """Read complete typed views without lossy IDs or dict-shaped rows."""

    def get_research_cycle_identity(
        self, experiment_id: ExperimentId
    ) -> ResearchCycleIdentity | None: ...

    def get_launch_spec(
        self, experiment_id: ExperimentId
    ) -> ExperimentLaunchSpec | None: ...

    def get_experiment_projection(
        self, experiment_id: ExperimentId
    ) -> ExperimentProjection | None: ...

    def list_dispatchable_experiments(self) -> tuple[ExperimentProjection, ...]: ...

    def list_candidates(
        self, experiment_id: ExperimentId
    ) -> tuple[CandidateSpec, ...]: ...

    def get_fold(self, key: FoldKey) -> FoldView | None: ...

    def list_folds(self, experiment_id: ExperimentId) -> tuple[FoldView, ...]: ...

    def list_claimable_folds(
        self, experiment_id: ExperimentId
    ) -> tuple[FoldView, ...]: ...

    def get_attempt(self, attempt_id: AttemptId) -> AttemptView | None: ...

    def list_attempts(self, key: FoldKey) -> tuple[AttemptView, ...]: ...

    def list_status_events(
        self, experiment_id: ExperimentId
    ) -> tuple[StatusEventRecord, ...]: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None: ...

    def get_gate_evaluation(
        self, evaluation_id: str
    ) -> GateEvaluationRecord | None: ...

    def get_holdout_claim(self, claim_id: str) -> HoldoutClaimRecord | None: ...

    def get_scheduler_slot(self) -> SchedulerSlot: ...


class ExperimentWriterProtocol(Protocol):
    """Persist typed aggregates, append-only facts, and fenced CAS projections."""

    def create_experiment(
        self,
        cycle: ResearchCycleIdentity,
        spec: ExperimentLaunchSpec,
        initial_record: ExperimentRecord,
    ) -> None: ...

    def transition_experiment(
        self,
        experiment_id: ExperimentId,
        *,
        target_status: ExperimentStatus,
        target_desired_state: ExperimentDesiredState,
        target_stage: ExperimentStage,
        failure_code: ExperimentFailureCode | None,
        queue_ordinal: int | None,
        expected_revision: int,
        occurred_at: datetime,
        attempt_started: bool,
        precondition_repairable: bool,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection: ...

    def enqueue_experiment(
        self,
        experiment_id: ExperimentId,
        *,
        expected_revision: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection: ...

    def transition_scheduled_experiment(
        self,
        experiment_id: ExperimentId,
        *,
        target_status: ExperimentStatus,
        target_stage: ExperimentStage,
        failure_code: ExperimentFailureCode | None,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        attempt_started: bool,
        precondition_repairable: bool,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection: ...

    def advance_experiment_stage(
        self,
        experiment_id: ExperimentId,
        *,
        target_stage: ExperimentStage,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> ExperimentProjection: ...

    def add_fold(self, spec: FoldPersistenceSpec, initial: FoldProjection) -> None: ...

    def claim_fold(
        self,
        key: FoldKey,
        *,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> FoldProjection: ...

    def transition_fold(
        self,
        key: FoldKey,
        *,
        target_status: ExperimentStatus,
        claim_owner_token: str | None,
        failure_code: ExperimentFailureCode | None,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> FoldProjection: ...

    def add_attempt(
        self,
        spec: AttemptPersistenceSpec,
        initial: AttemptProjection,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> None: ...

    def claim_fold_and_add_attempt(
        self,
        key: FoldKey,
        spec: AttemptPersistenceSpec,
        initial: AttemptProjection,
        *,
        expected_fold_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
    ) -> tuple[FoldProjection, AttemptProjection]: ...

    def transition_attempt(
        self,
        attempt_id: AttemptId,
        *,
        target_status: ExperimentStatus,
        backtest_run_id: BacktestRunId | None,
        checkpoint_ref: CheckpointRef | None,
        failure_code: ExperimentFailureCode | None,
        expected_revision: int,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        occurred_at: datetime,
        reason_code: str | None,
        detail: Mapping[str, object],
    ) -> AttemptProjection: ...

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> None: ...

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
    ) -> ArtifactRecord: ...

    def add_gate_evaluation(self, record: GateEvaluationRecord) -> None: ...

    def claim_holdout(self, record: HoldoutClaimRecord) -> HoldoutClaimRecord: ...

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
        fence: LeaseFence,
        *,
        now_epoch_us: int,
        new_lease_until_epoch_us: int,
    ) -> SchedulerLease: ...

    def release_lease(
        self, fence: LeaseFence, *, now_epoch_us: int
    ) -> SchedulerSlot: ...
