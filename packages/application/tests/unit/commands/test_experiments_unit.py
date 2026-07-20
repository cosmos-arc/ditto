"""Unit tests for the research experiment launch command boundary."""

from __future__ import annotations

from typing import cast
from unittest.mock import Mock

import pytest
from ditto_application.commands.experiments import (
    LaunchExperimentCommand,
    LaunchExperimentHandler,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPlanningProcess,
    ExperimentPlanningRequest,
)


def _request() -> ExperimentPlanningRequest:
    request = Mock(spec=ExperimentPlanningRequest)
    request.experiment_id = "exp-command-1"
    return cast("ExperimentPlanningRequest", request)


def _receipt() -> ExperimentLaunchReceipt:
    return ExperimentLaunchReceipt(
        experiment_id="exp-command-1",
        status="queued",
        queue_ordinal=3,
        revision=1,
        candidate_count=2,
        fold_count=6,
        plan_hash="a" * 64,
    )


class _ProcessDouble:
    def __init__(
        self,
        *,
        receipt: ExperimentLaunchReceipt | None = None,
        error: AppProcessError | None = None,
    ) -> None:
        self.receipt = receipt
        self.error = error
        self.calls: list[tuple[ExperimentPlanningRequest, str]] = []

    def launch(
        self,
        request: ExperimentPlanningRequest,
        *,
        confirmed_plan_hash: str,
    ) -> ExperimentLaunchReceipt:
        self.calls.append((request, confirmed_plan_hash))
        if self.error is not None:
            raise self.error
        assert self.receipt is not None
        return self.receipt


def test_launch_handler_delegates_exact_request_and_confirmed_hash() -> None:
    request = _request()
    receipt = _receipt()
    process = _ProcessDouble(receipt=receipt)
    handler = LaunchExperimentHandler(
        cast("ExperimentPlanningProcess", process),
    )
    command = LaunchExperimentCommand(
        request=request,
        confirmed_plan_hash="a" * 64,
    )

    result = handler.handle(command)

    assert result is receipt
    assert process.calls == [(request, "a" * 64)]


def test_launch_handler_translates_process_error_with_command_context() -> None:
    process_error = AppProcessError(
        "confirmed experiment plan hash is stale",
        details={
            "code": "PLAN_HASH_MISMATCH",
            "reason": "stale_confirmation",
            "expected_plan_hash": "b" * 64,
        },
    )
    process = _ProcessDouble(error=process_error)
    handler = LaunchExperimentHandler(
        cast("ExperimentPlanningProcess", process),
    )

    with pytest.raises(AppCommandError) as exc_info:
        handler.handle(
            LaunchExperimentCommand(
                request=_request(),
                confirmed_plan_hash="a" * 64,
            ),
        )

    assert str(exc_info.value) == "confirmed experiment plan hash is stale"
    assert exc_info.value.details == {
        "code": "PLAN_HASH_MISMATCH",
        "reason": "stale_confirmation",
        "expected_plan_hash": "b" * 64,
        "command": "launch_experiment",
        "experiment_id": "exp-command-1",
    }
    assert exc_info.value.__cause__ is process_error
