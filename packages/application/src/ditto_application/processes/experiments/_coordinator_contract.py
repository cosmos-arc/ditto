"""Small typed contracts shared by the durable experiment coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ditto_application.processes.experiments._coordinator_snapshot import (
    scheduler_error,
)
from ditto_application.processes.experiments.scheduler_store import (
    AttemptView,
    CheckpointRef,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldView,
)

__all__ = [
    "ExperimentControlReceipt",
    "ExperimentDispatch",
    "ExperimentProgress",
    "PersistedAttemptStart",
    "SchedulerTickResult",
    "SchedulerTickState",
]

_REPLAYABLE_TERMINAL_ATTEMPT = frozenset(
    {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED}
)
_REPLAYABLE_FAILURES = frozenset(
    {
        ExperimentFailureCode.CANDIDATE_FAILED,
        ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ExperimentFailureCode.SYSTEM_ERROR,
    }
)


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
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ExperimentControlReceipt:
    """Pure durable projection returned before best-effort notification."""

    experiment_id: str
    status: str
    desired_state: str
    revision: int
    occurred_at: datetime
    live_run_ids: tuple[str, ...] = ()


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
    """One durably claimed attempt ready for execution-owned audit work."""

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
        run_id = self.attempt.projection.backtest_run_id
        checkpoint = self.attempt.projection.checkpoint_ref
        base_invalid = (
            type(self.attempt) is not AttemptView
            or type(self.fold) is not FoldView
            or type(self.started_now) is not bool
            or self.attempt.spec.attempt_id != self.attempt.projection.attempt_id
            or self.fold.spec.key != self.fold.projection.key
            or self.attempt.spec.fold_key != self.fold.spec.key
            or run_id is None
            or (checkpoint is not None and checkpoint != CheckpointRef(str(run_id)))
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
                    and self.attempt.projection.failure_code in _REPLAYABLE_FAILURES
                )
            )
        )
        if base_invalid or not (running or terminal):
            raise scheduler_error(
                "EXPERIMENT_INTEGRITY_FAILED",
                "persisted_attempt_start_invalid",
            )


@dataclass(frozen=True, slots=True)
class SchedulerTickResult:
    """Bounded result of one durable scheduling tick."""

    state: SchedulerTickState
    experiment_id: ExperimentId | None
    dispatches: tuple[ExperimentDispatch, ...]
    progress: ExperimentProgress | None
