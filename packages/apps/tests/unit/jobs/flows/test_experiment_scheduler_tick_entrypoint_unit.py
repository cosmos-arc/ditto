"""Unit tests for the run_experiment_scheduler_tick composition-root entrypoint."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

from ditto_apps.jobs.flows import experiments as experiments_module
from ditto_apps.registry.contexts.bundle import ExperimentExecutionBundle


def test_run_experiment_scheduler_tick_adapts_bundle_into_runtime_and_calls_flow(
    mocker,
) -> None:
    """Adapt the bundle into ExperimentTickRuntime and call the flow."""
    coordinator = MagicMock()
    worker = MagicMock()
    bundle = ExperimentExecutionBundle(coordinator=coordinator, worker=worker)

    @contextmanager
    def fake_bundle():
        yield bundle

    mocker.patch.object(
        experiments_module,
        "create_experiment_tick_bundle",
        fake_bundle,
    )
    flow = mocker.patch.object(
        experiments_module,
        "experiment_scheduler_tick_flow",
        return_value={"state": "idle"},
    )

    occurred_at = datetime(2026, 7, 26, 10, 0, 0, tzinfo=UTC)
    result = experiments_module.run_experiment_scheduler_tick(occurred_at=occurred_at)

    assert result == {"state": "idle"}
    assert flow.call_count == 1
    runtime = flow.call_args.kwargs["runtime"]
    assert runtime.coordinator is coordinator
    assert runtime.worker is worker
    assert flow.call_args.kwargs["occurred_at"] is occurred_at


def test_run_experiment_scheduler_tick_propagates_flow_result(mocker) -> None:
    """Whatever the flow returns must be returned unchanged (no post-processing)."""

    @contextmanager
    def fake_bundle():
        yield ExperimentExecutionBundle(
            coordinator=MagicMock(),
            worker=MagicMock(),
        )

    mocker.patch.object(
        experiments_module,
        "create_experiment_tick_bundle",
        fake_bundle,
    )
    mocker.patch.object(
        experiments_module,
        "experiment_scheduler_tick_flow",
        return_value={
            "state": "dispatched",
            "experiment_id": "exp-1",
            "dispatch_count": 2,
        },
    )

    result = experiments_module.run_experiment_scheduler_tick(
        occurred_at=datetime(2026, 7, 26, 10, 0, 0, tzinfo=UTC),
    )

    assert result["state"] == "dispatched"
    assert result["experiment_id"] == "exp-1"
    assert result["dispatch_count"] == 2


def test_run_experiment_scheduler_tick_requires_utc_occurred_at(mocker) -> None:
    """A naive occurred_at must surface the underlying flow's UTC invariant."""

    @contextmanager
    def fake_bundle():
        yield ExperimentExecutionBundle(
            coordinator=MagicMock(),
            worker=MagicMock(),
        )

    mocker.patch.object(
        experiments_module,
        "create_experiment_tick_bundle",
        fake_bundle,
    )

    import pytest

    with pytest.raises(ValueError, match="occurred_at_must_be_utc"):
        experiments_module.run_experiment_scheduler_tick(
            occurred_at=datetime(2026, 7, 26, 10, 0, 0),
        )
