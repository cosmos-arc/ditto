"""Small result contracts shared by the durable experiment worker."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ditto_application.processes.experiments.scheduler_store import (
    AttemptId,
    BacktestRunId,
    ContentHash,
    ExperimentFailureCode,
)

__all__ = ["ResearchWorkerResult", "ResearchWorkerState"]


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
