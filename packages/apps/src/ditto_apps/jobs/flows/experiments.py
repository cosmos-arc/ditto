"""Explicit, bounded Prefect entrypoint for one durable experiment tick."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast

from ditto_application.processes.experiments.coordinator import (
    ExperimentDispatch,
    ExperimentProgress,
    SchedulerTickResult,
    SchedulerTickState,
    deterministic_backtest_run_id,
)
from ditto_application.processes.experiments.worker import (
    ResearchWorkerResult,
    ResearchWorkerState,
)
from prefect import flow

__all__ = ["ExperimentTickRuntime", "experiment_scheduler_tick_flow"]

_ALLOWED_WORKER_LIMITS = frozenset({2, 4})
_THREAD_NAME_PREFIX = "ditto-research-worker"
_EXECUTABLE_STAGE_ROLES = {
    "exploration": "exploration",
    "walk_forward": "walk_forward",
}
_WORKER_STATE_FAILURE_PAIRS = frozenset(
    {
        (ResearchWorkerState.COMPLETED, None),
        (ResearchWorkerState.PAUSED, None),
        (ResearchWorkerState.CANCELLED, None),
        (ResearchWorkerState.CANDIDATE_FAILED, "candidate_failed"),
        (ResearchWorkerState.INPUT_FAILED, "input_hash_mismatch"),
        (ResearchWorkerState.SYSTEM_FAILED, "system_error"),
    }
)


class _TickCoordinator(Protocol):
    def tick(self, *, occurred_at: datetime) -> SchedulerTickResult:
        """Claim at most one persisted worker-capacity batch."""
        ...


class _TickWorker(Protocol):
    def execute(
        self,
        dispatch: ExperimentDispatch,
        *,
        occurred_at: datetime,
    ) -> ResearchWorkerResult:
        """Execute one already claimed durable dispatch."""
        ...


@dataclass(frozen=True, slots=True)
class ExperimentTickRuntime:
    """
    Complete runtime supplied explicitly by a composition root.

    Task 9 intentionally has no implicit container fallback. The concrete frozen
    artifact resolver and research backtest factory are wired only after their
    content-addressed storage boundary exists.
    """

    coordinator: _TickCoordinator
    worker: _TickWorker


def _require_utc(value: datetime) -> None:
    raw: object = value
    if (
        type(raw) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError("occurred_at_must_be_utc")


def _validate_tick(result: SchedulerTickResult) -> int | None:
    if type(cast("object", result)) is not SchedulerTickResult:
        raise ValueError("invalid_scheduler_tick_result")
    progress = result.progress
    dispatch_count = len(result.dispatches)
    if progress is None:
        if dispatch_count:
            raise ValueError("dispatched_tick_requires_persisted_progress")
        return None
    if result.experiment_id != progress.experiment_id:
        raise ValueError("scheduler_progress_lineage_mismatch")
    worker_limit = progress.worker_limit
    if worker_limit not in _ALLOWED_WORKER_LIMITS:
        raise ValueError("worker_limit_must_be_two_or_four")
    if dispatch_count > worker_limit:
        raise ValueError("dispatch_count_exceeds_worker_limit")
    if progress.live_attempt_count > worker_limit:
        raise ValueError("persisted_live_attempt_count_exceeds_worker_limit")
    if dispatch_count and result.state is not SchedulerTickState.DISPATCHED:
        raise ValueError("scheduler_dispatch_state_mismatch")
    if not dispatch_count and result.state is SchedulerTickState.DISPATCHED:
        raise ValueError("dispatched_tick_requires_dispatches")
    _validate_dispatch_batch(result, progress)
    return worker_limit


def _validate_dispatch_batch(
    result: SchedulerTickResult,
    progress: ExperimentProgress,
) -> None:
    """Validate the entire durable batch before any worker thread can start."""
    attempt_ids: set[object] = set()
    fold_keys: set[object] = set()
    for dispatch in result.dispatches:
        if type(cast("object", dispatch)) is not ExperimentDispatch:
            raise ValueError("invalid_experiment_dispatch")
        attempt = dispatch.attempt.spec
        fold = dispatch.fold.spec
        expected_role = _EXECUTABLE_STAGE_ROLES.get(dispatch.stage.value)
        if expected_role is None or fold.fold_role.value != expected_role:
            raise ValueError("dispatch_stage_role_mismatch")
        if dispatch.stage is not progress.stage:
            raise ValueError("dispatch_progress_stage_mismatch")
        if (
            fold.key.experiment_id != result.experiment_id
            or attempt.fold_key.experiment_id != result.experiment_id
            or attempt.fold_key != fold.key
        ):
            raise ValueError("dispatch_experiment_lineage_mismatch")
        if attempt.attempt_id in attempt_ids:
            raise ValueError("duplicate_dispatch_attempt_id")
        if fold.key in fold_keys:
            raise ValueError("duplicate_dispatch_fold_key")
        attempt_ids.add(attempt.attempt_id)
        fold_keys.add(fold.key)


def _execute_dispatches(
    runtime: ExperimentTickRuntime,
    result: SchedulerTickResult,
    *,
    occurred_at: datetime,
    worker_limit: int | None,
) -> tuple[ResearchWorkerResult, ...]:
    if not result.dispatches:
        return ()
    if worker_limit is None:
        raise ValueError("dispatched_tick_requires_persisted_progress")

    def execute(dispatch: ExperimentDispatch) -> ResearchWorkerResult:
        return runtime.worker.execute(dispatch, occurred_at=occurred_at)

    with ThreadPoolExecutor(
        max_workers=worker_limit,
        thread_name_prefix=_THREAD_NAME_PREFIX,
    ) as executor:
        worker_results = tuple(executor.map(execute, result.dispatches))

    for dispatch, worker_result in zip(
        result.dispatches,
        worker_results,
        strict=True,
    ):
        if type(cast("object", worker_result)) is not ResearchWorkerResult:
            raise ValueError("invalid_research_worker_result")
        attempt = dispatch.attempt.spec
        if worker_result.attempt_id != attempt.attempt_id:
            raise ValueError("worker_result_attempt_identity_mismatch")
        if worker_result.reproduction_fingerprint != attempt.reproduction_fingerprint:
            raise ValueError("worker_result_reproduction_fingerprint_mismatch")
        if worker_result.backtest_run_id != deterministic_backtest_run_id(
            attempt.attempt_id,
            attempt.reproduction_fingerprint,
        ):
            raise ValueError("worker_result_backtest_run_identity_mismatch")
        failure_code = (
            None
            if worker_result.failure_code is None
            else worker_result.failure_code.value
        )
        if (worker_result.state, failure_code) not in _WORKER_STATE_FAILURE_PAIRS:
            raise ValueError("worker_result_state_failure_code_mismatch")
    return worker_results


def _progress_at_dispatch_payload(
    progress: ExperimentProgress | None,
) -> dict[str, object] | None:
    """Serialize the coordinator's DB-derived snapshot without refreshing it."""
    if progress is None:
        return None
    return {
        "stage": progress.stage.value,
        "worker_limit": progress.worker_limit,
        "available_capacity": progress.available_capacity,
        "total_fold_count": progress.total_fold_count,
        "terminal_fold_count": progress.terminal_fold_count,
        "live_attempt_count": progress.live_attempt_count,
        "completed_attempt_count": progress.completed_attempt_count,
        "failed_candidate_attempt_count": progress.failed_candidate_attempt_count,
        "hard_failure_count": progress.hard_failure_count,
    }


def _worker_payload(result: ResearchWorkerResult) -> dict[str, object]:
    return {
        "attempt_id": str(result.attempt_id),
        "backtest_run_id": str(result.backtest_run_id),
        "reproduction_fingerprint": str(result.reproduction_fingerprint),
        "state": result.state.value,
        "failure_code": (
            None if result.failure_code is None else result.failure_code.value
        ),
        "error_type": result.error_type,
    }


@flow(
    name="research-experiment-scheduler-tick",
    description="执行一次显式有界、lease-fenced 的 research experiment tick",
)
def experiment_scheduler_tick_flow(
    *,
    runtime: ExperimentTickRuntime,
    occurred_at: datetime,
) -> dict[str, object]:
    """Run one tick and return its DB-derived progress-at-dispatch snapshot."""
    _require_utc(occurred_at)
    scheduler_result = runtime.coordinator.tick(occurred_at=occurred_at)
    worker_limit = _validate_tick(scheduler_result)
    worker_results = _execute_dispatches(
        runtime,
        scheduler_result,
        occurred_at=occurred_at,
        worker_limit=worker_limit,
    )
    return {
        "state": scheduler_result.state.value,
        "experiment_id": (
            None
            if scheduler_result.experiment_id is None
            else str(scheduler_result.experiment_id)
        ),
        "dispatch_count": len(scheduler_result.dispatches),
        "progress_at_dispatch": _progress_at_dispatch_payload(
            scheduler_result.progress
        ),
        "worker_results": [_worker_payload(item) for item in worker_results],
    }
