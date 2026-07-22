"""Recovery contracts for experiment attempts and cooperative worker control."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime
from typing import cast

import pytest
from ditto_analysis.experiments import (
    AttemptView,
    BacktestRunId,
    CheckpointRef,
    ExperimentStatus,
)
from ditto_application.processes.experiments.scheduler_store import (
    QueuedAttempt,
    ResearchExecutionDirective,
)
from ditto_application.processes.experiments.worker import (
    ExecutionBundleFirstAttemptFactory,
    ResearchExperimentWorker,
    ResearchWorkerState,
)
from packages.application.tests.unit.process.experiments import (
    test_worker_unit as worker_fixtures,
)


def _terminal_parent(*, checkpointed: bool) -> AttemptView:
    dispatch = worker_fixtures._dispatch()
    return replace(
        dispatch.attempt,
        projection=replace(
            dispatch.attempt.projection,
            status=ExperimentStatus.CANCELLED,
            backtest_run_id=BacktestRunId("research-run-parent"),
            checkpoint_ref=(
                CheckpointRef("research-run-parent") if checkpointed else None
            ),
            revision=3,
        ),
    )


@pytest.mark.parametrize("checkpointed", [False, True])
def test_successor_attempt_preserves_parent_lineage_and_fingerprint(
    checkpointed: bool,
) -> None:
    """A resumed/retried fold gets a new immutable attempt, never a rewrite."""
    resolver = worker_fixtures._Resolver(worker_fixtures._semantics())
    factory = ExecutionBundleFirstAttemptFactory(resolver)
    fold = worker_fixtures._fold(ExperimentStatus.QUEUED)
    parent = _terminal_parent(checkpointed=checkpointed)

    successor = factory.create_successor(
        fold,
        parent,
        resume_from_run_id=(
            parent.projection.backtest_run_id if checkpointed else None
        ),
        occurred_at=worker_fixtures._NOW,
    )

    assert type(successor) is QueuedAttempt
    assert successor.spec.attempt_id != parent.spec.attempt_id
    assert successor.spec.ordinal == parent.spec.ordinal + 1
    assert successor.spec.parent_attempt_id == parent.spec.attempt_id
    assert successor.spec.reproduction_fingerprint == (
        parent.spec.reproduction_fingerprint
    )
    assert successor.spec.resume_from_run_id == (
        parent.projection.backtest_run_id if checkpointed else None
    )
    assert successor.projection.status is ExperimentStatus.QUEUED
    assert successor.projection.backtest_run_id is None
    assert successor.projection.checkpoint_ref is None
    assert resolver.calls == 0


class _RecoveryCoordinator(worker_fixtures._Coordinator):
    def __init__(
        self,
        directives: Iterator[ResearchExecutionDirective],
    ) -> None:
        super().__init__()
        self._directives = directives

    def poll_execution_directive(
        self,
        attempt_id: object,
        *,
        occurred_at: datetime,
    ) -> ResearchExecutionDirective:
        self.calls.append(("directive", (attempt_id, occurred_at)))
        return next(self._directives)

    def record_checkpoint(
        self,
        attempt_id: object,
        checkpoint_ref: CheckpointRef,
        *,
        occurred_at: datetime,
    ) -> object:
        self.calls.append(
            ("checkpoint", (attempt_id, checkpoint_ref, occurred_at)),
        )
        return cast("object", object())

    def cooperative_stop_attempt(
        self,
        attempt_id: object,
        directive: ResearchExecutionDirective,
        *,
        occurred_at: datetime,
    ) -> object:
        self.calls.append(("stop", (attempt_id, directive, occurred_at)))
        return cast("object", object())


@pytest.mark.parametrize(
    ("directive", "expected_state"),
    [
        (ResearchExecutionDirective.PAUSE, ResearchWorkerState.PAUSED),
        (ResearchExecutionDirective.CANCEL, ResearchWorkerState.CANCELLED),
    ],
)
def test_running_worker_treats_durable_stop_as_control_not_system_failure(
    directive: ResearchExecutionDirective,
    expected_state: ResearchWorkerState,
) -> None:
    """Pause/cancel exits preserve checkpoint lineage and never call fail_attempt."""
    coordinator = _RecoveryCoordinator(
        iter(
            (
                ResearchExecutionDirective.RUN,
                ResearchExecutionDirective.RUN,
                ResearchExecutionDirective.RUN,
                directive,
            ),
        ),
    )
    worker = ResearchExperimentWorker(
        coordinator=coordinator,
        semantics_resolver=worker_fixtures._Resolver(worker_fixtures._semantics()),
        runner=worker_fixtures._Runner(poll_control=True),
        checkpoint_available=lambda run_id: run_id == "research-run-persisted",
        clock=lambda: worker_fixtures._NOW,
    )

    result = worker.execute(
        worker_fixtures._dispatch(),
        occurred_at=worker_fixtures._NOW,
    )

    assert result.state is expected_state
    assert result.failure_code is None
    assert result.error_type is None
    names = [name for name, _payload in coordinator.calls]
    assert "checkpoint" in names
    assert "stop" in names
    assert "fail" not in names
    checkpoint_call = next(
        payload for name, payload in coordinator.calls if name == "checkpoint"
    )
    assert checkpoint_call[1] == CheckpointRef("research-run-persisted")


def test_control_before_attempt_start_does_not_run_numerics() -> None:
    """A queued delivery observes persisted cancel intent before start transition."""
    coordinator = _RecoveryCoordinator(iter((ResearchExecutionDirective.CANCEL,)))
    runner = worker_fixtures._Runner()
    resolver = worker_fixtures._Resolver(worker_fixtures._semantics())
    worker = ResearchExperimentWorker(
        coordinator=coordinator,
        semantics_resolver=resolver,
        runner=runner,
        checkpoint_available=lambda _run_id: False,
        clock=lambda: worker_fixtures._NOW,
    )

    result = worker.execute(
        worker_fixtures._dispatch(),
        occurred_at=worker_fixtures._NOW,
    )

    assert result.state is ResearchWorkerState.CANCELLED
    assert resolver.calls == 0
    assert runner.audits == []
    assert [name for name, _payload in coordinator.calls] == [
        "renew",
        "directive",
        "renew",
        "stop",
    ]
