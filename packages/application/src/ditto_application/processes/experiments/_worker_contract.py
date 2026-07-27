"""Small result contracts shared by the durable experiment worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentDispatch,
    PersistedAttemptStart,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportEvidence,
)
from ditto_application.processes.experiments.lease_authority import (
    RenewedLeaseOperation,
)
from ditto_application.processes.experiments.scheduler_store import (
    AttemptId,
    BacktestRunId,
    CheckpointRef,
    ContentHash,
    ExperimentFailureCode,
    ResearchExecutionDirective,
    SchedulerLease,
)

__all__ = [
    "ResearchFoldRunResult",
    "ResearchFoldRunState",
    "ResearchWorkerCoordinator",
    "ResearchWorkerResult",
    "ResearchWorkerState",
]


def _worker_contract_error(reason: str) -> AppProcessError:
    return AppProcessError(
        "research experiment worker contract is invalid",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
        },
    )


class ResearchFoldRunState(StrEnum):
    """Typed numerical runner outcome consumed by the durable worker."""

    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class ResearchFoldRunResult:
    """Exact numerical outcome; completed runs always carry report evidence."""

    state: ResearchFoldRunState
    report_evidence: BacktestReportEvidence | None

    def __post_init__(self) -> None:
        """Keep stopped partial reports out of the durable evidence path."""
        valid = (
            self.state is ResearchFoldRunState.COMPLETED
            and type(self.report_evidence) is BacktestReportEvidence
        ) or (
            self.state is ResearchFoldRunState.STOPPED and self.report_evidence is None
        )
        if type(cast("object", self.state)) is not ResearchFoldRunState or not valid:
            raise _worker_contract_error("invalid_research_fold_run_result")


class ResearchWorkerCoordinator(Protocol):
    """Narrow lease-fenced coordinator operations owned by the worker."""

    def renew_lease(self, *, occurred_at: datetime) -> SchedulerLease: ...

    def publish_attempt_artifact[ResultT](
        self,
        operation: RenewedLeaseOperation[ResultT],
    ) -> ResultT: ...

    def start_attempt(
        self,
        dispatch: ExperimentDispatch,
        *,
        occurred_at: datetime,
    ) -> PersistedAttemptStart: ...

    def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        occurred_at: datetime,
    ) -> object: ...

    def fail_attempt(
        self,
        attempt_id: AttemptId,
        failure_code: ExperimentFailureCode,
        *,
        occurred_at: datetime,
    ) -> object: ...

    def poll_execution_directive(
        self,
        attempt_id: AttemptId,
        *,
        occurred_at: datetime,
    ) -> ResearchExecutionDirective: ...

    def record_checkpoint(
        self,
        attempt_id: AttemptId,
        checkpoint_ref: CheckpointRef,
        *,
        occurred_at: datetime,
    ) -> object: ...

    def cooperative_stop_attempt(
        self,
        attempt_id: AttemptId,
        directive: ResearchExecutionDirective,
        *,
        occurred_at: datetime,
    ) -> object: ...


class ResearchWorkerState(StrEnum):
    """Stable one-attempt worker outcome."""

    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    CANDIDATE_FAILED = "candidate_failed"
    INPUT_FAILED = "input_failed"
    SYSTEM_FAILED = "system_failed"


@dataclass(frozen=True, slots=True)
class ResearchWorkerResult:
    """Serializable worker result derived from a durable attempt transition."""

    attempt_id: AttemptId
    backtest_run_id: BacktestRunId
    reproduction_fingerprint: ContentHash
    state: ResearchWorkerState
    failure_code: ExperimentFailureCode | None
    error_type: str | None
