"""Unit tests for one bounded durable experiment scheduler tick."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
    canonical_payload,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentDispatch,
    ExperimentProgress,
    SchedulerTickResult,
    SchedulerTickState,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
)
from ditto_application.processes.experiments.worker import (
    ResearchWorkerResult,
    ResearchWorkerState,
)
from ditto_application.providers_process import AppProcessProvider
from ditto_apps.jobs.flows.experiments import (
    ExperimentTickRuntime,
    experiment_scheduler_tick_flow,
)
from pytest_mock import MockerFixture

_NOW = datetime(2026, 7, 20, 10, tzinfo=UTC)
_FINGERPRINT = ContentHash("a" * 64)


def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


EXPERIMENT_TICK_FLOW_RUNNER = _prefect_runner(experiment_scheduler_tick_flow)


def _expected_run_id(dispatch: ExperimentDispatch) -> BacktestRunId:
    attempt = dispatch.attempt.spec
    identity = canonical_payload(
        {
            "kind": "r3_research_backtest_run",
            "attempt_id": str(attempt.attempt_id),
            "reproduction_fingerprint": str(attempt.reproduction_fingerprint),
        }
    ).content_hash
    return BacktestRunId(f"research-run-{identity}")


def _dispatch(
    index: int,
    *,
    experiment_id: ExperimentId = ExperimentId("experiment-1"),
    stage: ExperimentStage = ExperimentStage.EXPLORATION,
    fold_role: FoldRole = FoldRole.EXPLORATION,
) -> ExperimentDispatch:
    attempt_id = AttemptId(f"attempt-{index}")
    fold_key = FoldKey(
        experiment_id=experiment_id,
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId(f"fold-{index}"),
    )
    fold_spec = FoldPersistenceSpec.create(
        key=fold_key,
        ordinal=index + 1,
        fold_role=fold_role,
        train_window=DateWindow(date(2024, 1, 2), date(2024, 1, 31)),
        test_window=DateWindow(date(2024, 2, 1), date(2024, 2, 29)),
        purge_sessions=1,
        embargo_sessions=1,
    )
    fold = FoldView(
        spec=fold_spec,
        projection=FoldProjection(
            key=fold_key,
            status=ExperimentStatus.RUNNING,
            claim_owner_token="owner-1",
            created_at=_NOW,
            updated_at=_NOW,
            revision=1,
        ),
    )
    attempt = AttemptView(
        spec=AttemptPersistenceSpec(
            attempt_id=attempt_id,
            fold_key=fold_key,
            ordinal=1,
            parent_attempt_id=None,
            resume_from_run_id=None,
            reproduction_fingerprint=_FINGERPRINT,
            created_at=_NOW,
        ),
        projection=AttemptProjection(
            attempt_id=attempt_id,
            status=ExperimentStatus.QUEUED,
            backtest_run_id=None,
            checkpoint_ref=None,
            failure_code=None,
            created_at=_NOW,
            updated_at=_NOW,
            revision=0,
        ),
    )
    return ExperimentDispatch(stage=stage, fold=fold, attempt=attempt)


def _progress(worker_limit: int, *, live_attempt_count: int) -> ExperimentProgress:
    return ExperimentProgress(
        experiment_id=ExperimentId("experiment-1"),
        stage=ExperimentStage.EXPLORATION,
        worker_limit=worker_limit,
        available_capacity=max(0, worker_limit - live_attempt_count),
        total_fold_count=8,
        terminal_fold_count=1,
        live_attempt_count=live_attempt_count,
        completed_attempt_count=1,
        failed_candidate_attempt_count=0,
        hard_failure_count=0,
    )


def _tick_result(
    dispatch_count: int,
    *,
    worker_limit: int = 2,
) -> SchedulerTickResult:
    dispatches = tuple(_dispatch(index) for index in range(dispatch_count))
    return SchedulerTickResult(
        state=SchedulerTickState.DISPATCHED,
        experiment_id=ExperimentId("experiment-1"),
        dispatches=dispatches,
        progress=_progress(worker_limit, live_attempt_count=dispatch_count),
    )


class _Coordinator:
    def __init__(self, result: SchedulerTickResult) -> None:
        self.result = result
        self.occurred_at_calls: list[datetime] = []

    def tick(self, *, occurred_at: datetime) -> SchedulerTickResult:
        self.occurred_at_calls.append(occurred_at)
        return self.result


class _Worker:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[AttemptId, datetime]] = []

    def execute(
        self,
        dispatch: ExperimentDispatch,
        *,
        occurred_at: datetime,
    ) -> ResearchWorkerResult:
        attempt_id = dispatch.attempt.spec.attempt_id
        self.calls.append((attempt_id, occurred_at))
        if self.error is not None:
            raise self.error
        return ResearchWorkerResult(
            attempt_id=attempt_id,
            backtest_run_id=_expected_run_id(dispatch),
            reproduction_fingerprint=dispatch.attempt.spec.reproduction_fingerprint,
            state=ResearchWorkerState.COMPLETED,
            failure_code=None,
            error_type=None,
        )


class _ResultWorker:
    def __init__(self, result: ResearchWorkerResult) -> None:
        self.result = result
        self.calls: list[tuple[AttemptId, datetime]] = []

    def execute(
        self,
        dispatch: ExperimentDispatch,
        *,
        occurred_at: datetime,
    ) -> ResearchWorkerResult:
        self.calls.append((dispatch.attempt.spec.attempt_id, occurred_at))
        return self.result


def _worker_result(
    dispatch: ExperimentDispatch,
    *,
    state: ResearchWorkerState = ResearchWorkerState.COMPLETED,
    failure_code: ExperimentFailureCode | None = None,
) -> ResearchWorkerResult:
    return ResearchWorkerResult(
        attempt_id=dispatch.attempt.spec.attempt_id,
        backtest_run_id=_expected_run_id(dispatch),
        reproduction_fingerprint=dispatch.attempt.spec.reproduction_fingerprint,
        state=state,
        failure_code=failure_code,
        error_type=None if failure_code is None else "RuntimeError",
    )


def test_provider_registers_only_closed_scheduler_store_boundary() -> None:
    """Provider wiring must not invent unresolved artifact/runtime adapters."""
    reader = cast("object", SimpleNamespace())
    writer = cast("object", SimpleNamespace())

    store = AppProcessProvider().experiment_scheduler_store(reader, writer)

    assert isinstance(store, ExperimentSchedulerStore)


@pytest.mark.parametrize("worker_limit", [2, 4])
def test_flow_executes_only_one_bounded_tick_and_returns_durable_results(
    worker_limit: int,
    mocker: MockerFixture,
) -> None:
    """One flow run uses the persisted 2/4 bound and preserves dispatch order."""
    coordinator = _Coordinator(_tick_result(worker_limit, worker_limit=worker_limit))
    worker = _Worker()
    executor = mocker.patch(
        "ditto_apps.jobs.flows.experiments.ThreadPoolExecutor",
        wraps=RealThreadPoolExecutor,
    )

    result = EXPERIMENT_TICK_FLOW_RUNNER(
        runtime=ExperimentTickRuntime(coordinator=coordinator, worker=worker),
        occurred_at=_NOW,
    )

    executor.assert_called_once_with(
        max_workers=worker_limit,
        thread_name_prefix="ditto-research-worker",
    )
    assert coordinator.occurred_at_calls == [_NOW]
    assert sorted(
        (str(attempt_id), occurred_at) for attempt_id, occurred_at in worker.calls
    ) == [(f"attempt-{index}", _NOW) for index in range(worker_limit)]
    assert result == {
        "state": "dispatched",
        "experiment_id": "experiment-1",
        "dispatch_count": worker_limit,
        "progress_at_dispatch": {
            "stage": "exploration",
            "worker_limit": worker_limit,
            "available_capacity": 0,
            "total_fold_count": 8,
            "terminal_fold_count": 1,
            "live_attempt_count": worker_limit,
            "completed_attempt_count": 1,
            "failed_candidate_attempt_count": 0,
            "hard_failure_count": 0,
        },
        "worker_results": [
            {
                "attempt_id": f"attempt-{index}",
                "backtest_run_id": str(_expected_run_id(_dispatch(index))),
                "reproduction_fingerprint": "a" * 64,
                "state": "completed",
                "failure_code": None,
                "error_type": None,
            }
            for index in range(worker_limit)
        ],
    }


def test_idle_flow_returns_scheduler_truth_without_starting_executor(
    mocker: MockerFixture,
) -> None:
    coordinator = _Coordinator(
        SchedulerTickResult(
            state=SchedulerTickState.IDLE,
            experiment_id=None,
            dispatches=(),
            progress=None,
        )
    )
    worker = _Worker()
    executor = mocker.patch("ditto_apps.jobs.flows.experiments.ThreadPoolExecutor")

    result = EXPERIMENT_TICK_FLOW_RUNNER(
        runtime=ExperimentTickRuntime(coordinator=coordinator, worker=worker),
        occurred_at=_NOW,
    )

    executor.assert_not_called()
    assert worker.calls == []
    assert result == {
        "state": "idle",
        "experiment_id": None,
        "dispatch_count": 0,
        "progress_at_dispatch": None,
        "worker_results": [],
    }


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (_tick_result(1, worker_limit=3), "worker_limit_must_be_two_or_four"),
        (_tick_result(3, worker_limit=2), "dispatch_count_exceeds_worker_limit"),
        (
            SchedulerTickResult(
                state=SchedulerTickState.DISPATCHED,
                experiment_id=ExperimentId("experiment-1"),
                dispatches=(_dispatch(1),),
                progress=None,
            ),
            "dispatched_tick_requires_persisted_progress",
        ),
    ],
)
def test_flow_fails_closed_on_invalid_bounded_tick_contract(
    result: SchedulerTickResult,
    reason: str,
) -> None:
    coordinator = _Coordinator(result)
    worker = _Worker()

    with pytest.raises(ValueError, match=reason):
        EXPERIMENT_TICK_FLOW_RUNNER(
            runtime=ExperimentTickRuntime(coordinator=coordinator, worker=worker),
            occurred_at=_NOW,
        )

    assert worker.calls == []


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("duplicate_attempt", "duplicate_dispatch_attempt_id"),
        ("duplicate_fold", "duplicate_dispatch_fold_key"),
        ("result_progress_lineage", "scheduler_progress_lineage_mismatch"),
        ("fold_experiment_lineage", "dispatch_experiment_lineage_mismatch"),
        ("attempt_experiment_lineage", "dispatch_experiment_lineage_mismatch"),
        ("stage_role", "dispatch_stage_role_mismatch"),
        ("progress_stage", "dispatch_progress_stage_mismatch"),
    ],
)
def test_flow_rejects_dispatch_integrity_drift_before_starting_executor(
    case: str,
    reason: str,
    mocker: MockerFixture,
) -> None:
    """The flow must validate the complete claimed batch before starting threads."""
    first = _dispatch(0)
    second = _dispatch(1)
    experiment_id = ExperimentId("experiment-1")
    progress = _progress(2, live_attempt_count=2)

    if case == "duplicate_attempt":
        duplicate_id = first.attempt.spec.attempt_id
        second = replace(
            second,
            attempt=replace(
                second.attempt,
                spec=replace(second.attempt.spec, attempt_id=duplicate_id),
                projection=replace(
                    second.attempt.projection,
                    attempt_id=duplicate_id,
                ),
            ),
        )
    elif case == "duplicate_fold":
        second = replace(
            second,
            fold=first.fold,
            attempt=replace(
                second.attempt,
                spec=replace(
                    second.attempt.spec,
                    fold_key=first.fold.spec.key,
                ),
            ),
        )
    elif case == "result_progress_lineage":
        progress = replace(
            progress,
            experiment_id=ExperimentId("experiment-drift"),
        )
    elif case == "fold_experiment_lineage":
        second = _dispatch(1, experiment_id=ExperimentId("experiment-drift"))
    elif case == "attempt_experiment_lineage":
        attempt_key = replace(
            second.attempt.spec.fold_key,
            experiment_id=ExperimentId("experiment-drift"),
        )
        second = replace(
            second,
            attempt=replace(
                second.attempt,
                spec=replace(second.attempt.spec, fold_key=attempt_key),
            ),
        )
    elif case == "stage_role":
        first = _dispatch(
            0,
            stage=ExperimentStage.WALK_FORWARD,
            fold_role=FoldRole.EXPLORATION,
        )
    elif case == "progress_stage":
        progress = replace(progress, stage=ExperimentStage.WALK_FORWARD)
    else:  # pragma: no cover - exhaustive parameter fixture
        raise AssertionError(case)

    result = SchedulerTickResult(
        state=SchedulerTickState.DISPATCHED,
        experiment_id=experiment_id,
        dispatches=(first, second),
        progress=progress,
    )
    coordinator = _Coordinator(result)
    worker = _Worker()
    executor = mocker.patch("ditto_apps.jobs.flows.experiments.ThreadPoolExecutor")

    with pytest.raises(ValueError, match=reason):
        EXPERIMENT_TICK_FLOW_RUNNER(
            runtime=ExperimentTickRuntime(coordinator=coordinator, worker=worker),
            occurred_at=_NOW,
        )

    executor.assert_not_called()
    assert worker.calls == []


def test_flow_accepts_walk_forward_dispatch_with_walk_forward_fold() -> None:
    dispatch = _dispatch(
        0,
        stage=ExperimentStage.WALK_FORWARD,
        fold_role=FoldRole.WALK_FORWARD,
    )
    coordinator = _Coordinator(
        SchedulerTickResult(
            state=SchedulerTickState.DISPATCHED,
            experiment_id=ExperimentId("experiment-1"),
            dispatches=(dispatch,),
            progress=replace(
                _progress(2, live_attempt_count=1),
                stage=ExperimentStage.WALK_FORWARD,
            ),
        )
    )

    result = EXPERIMENT_TICK_FLOW_RUNNER(
        runtime=ExperimentTickRuntime(coordinator=coordinator, worker=_Worker()),
        occurred_at=_NOW,
    )

    assert result["progress_at_dispatch"] == {
        "stage": "walk_forward",
        "worker_limit": 2,
        "available_capacity": 1,
        "total_fold_count": 8,
        "terminal_fold_count": 1,
        "live_attempt_count": 1,
        "completed_attempt_count": 1,
        "failed_candidate_attempt_count": 0,
        "hard_failure_count": 0,
    }


def test_worker_exception_does_not_trigger_another_scheduler_tick() -> None:
    coordinator = _Coordinator(_tick_result(2))
    worker = _Worker(RuntimeError("worker exploded"))

    with pytest.raises(RuntimeError, match="worker exploded"):
        EXPERIMENT_TICK_FLOW_RUNNER(
            runtime=ExperimentTickRuntime(coordinator=coordinator, worker=worker),
            occurred_at=_NOW,
        )

    assert coordinator.occurred_at_calls == [_NOW]


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("fingerprint", "worker_result_reproduction_fingerprint_mismatch"),
        ("run_id", "worker_result_backtest_run_identity_mismatch"),
        ("completed_failure", "worker_result_state_failure_code_mismatch"),
        ("candidate_failure", "worker_result_state_failure_code_mismatch"),
        ("input_failure", "worker_result_state_failure_code_mismatch"),
        ("system_failure", "worker_result_state_failure_code_mismatch"),
    ],
)
def test_flow_rejects_worker_result_identity_or_failure_pair_drift(
    case: str,
    reason: str,
) -> None:
    dispatch = _dispatch(0)
    worker_result = _worker_result(dispatch)
    if case == "fingerprint":
        worker_result = replace(
            worker_result,
            reproduction_fingerprint=ContentHash("b" * 64),
        )
    elif case == "run_id":
        worker_result = replace(
            worker_result,
            backtest_run_id=BacktestRunId("research-run-drift"),
        )
    elif case == "completed_failure":
        worker_result = replace(
            worker_result,
            failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        )
    elif case == "candidate_failure":
        worker_result = replace(
            worker_result,
            state=ResearchWorkerState.CANDIDATE_FAILED,
            failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        )
    elif case == "input_failure":
        worker_result = replace(
            worker_result,
            state=ResearchWorkerState.INPUT_FAILED,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        )
    elif case == "system_failure":
        worker_result = replace(
            worker_result,
            state=ResearchWorkerState.SYSTEM_FAILED,
            failure_code=ExperimentFailureCode.INPUT_HASH_MISMATCH,
        )
    else:  # pragma: no cover - exhaustive parameter fixture
        raise AssertionError(case)
    coordinator = _Coordinator(
        SchedulerTickResult(
            state=SchedulerTickState.DISPATCHED,
            experiment_id=ExperimentId("experiment-1"),
            dispatches=(dispatch,),
            progress=_progress(2, live_attempt_count=1),
        )
    )
    worker = _ResultWorker(worker_result)

    with pytest.raises(ValueError, match=reason):
        EXPERIMENT_TICK_FLOW_RUNNER(
            runtime=ExperimentTickRuntime(coordinator=coordinator, worker=worker),
            occurred_at=_NOW,
        )

    assert worker.calls == [(dispatch.attempt.spec.attempt_id, _NOW)]


@pytest.mark.parametrize(
    ("state", "failure_code"),
    [
        (ResearchWorkerState.COMPLETED, None),
        (ResearchWorkerState.PAUSED, None),
        (ResearchWorkerState.CANCELLED, None),
        (
            ResearchWorkerState.CANDIDATE_FAILED,
            ExperimentFailureCode.CANDIDATE_FAILED,
        ),
        (
            ResearchWorkerState.INPUT_FAILED,
            ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ),
        (ResearchWorkerState.SYSTEM_FAILED, ExperimentFailureCode.SYSTEM_ERROR),
    ],
)
def test_flow_accepts_exact_worker_state_failure_code_pairs(
    state: ResearchWorkerState,
    failure_code: ExperimentFailureCode | None,
) -> None:
    dispatch = _dispatch(0)
    worker_result = _worker_result(
        dispatch,
        state=state,
        failure_code=failure_code,
    )
    coordinator = _Coordinator(
        SchedulerTickResult(
            state=SchedulerTickState.DISPATCHED,
            experiment_id=ExperimentId("experiment-1"),
            dispatches=(dispatch,),
            progress=_progress(2, live_attempt_count=1),
        )
    )

    result = EXPERIMENT_TICK_FLOW_RUNNER(
        runtime=ExperimentTickRuntime(
            coordinator=coordinator,
            worker=_ResultWorker(worker_result),
        ),
        occurred_at=_NOW,
    )

    assert result["worker_results"] == [
        {
            "attempt_id": "attempt-0",
            "backtest_run_id": str(_expected_run_id(dispatch)),
            "reproduction_fingerprint": "a" * 64,
            "state": state.value,
            "failure_code": None if failure_code is None else failure_code.value,
            "error_type": None if failure_code is None else "RuntimeError",
        }
    ]


def test_flow_requires_explicit_runtime_and_utc_event_time() -> None:
    coordinator = _Coordinator(_tick_result(0))
    worker = _Worker()

    with pytest.raises(ValueError, match="occurred_at_must_be_utc"):
        EXPERIMENT_TICK_FLOW_RUNNER(
            runtime=ExperimentTickRuntime(coordinator=coordinator, worker=worker),
            occurred_at=datetime(2026, 7, 20, 10),
        )

    assert coordinator.occurred_at_calls == []
