"""
Execution-owned immutable attempt and scheduler snapshot models.

Extracted from :mod:`scheduler_store` to keep it under its size budget. These
frozen dataclasses and the first-attempt factory protocol validate durable
scheduler invariants at the boundary between the experiment store and the
coordinator/worker that consume them. The store and protocol stay in
:mod:`scheduler_store`; only the value models live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from ditto_analysis.experiments import (
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentStatus,
    FoldView,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._holdout_contract import (
    PersistedHoldoutClaim,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)

__all__ = [
    "ExperimentSchedulerSnapshot",
    "FirstAttempt",
    "FirstAttemptFactory",
    "QueuedAttempt",
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
