"""Unit tests for the research experiment command boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock

import pytest
from ditto_application.commands.experiments import (
    CancelExperimentCommand,
    CancelExperimentHandler,
    ExperimentControlNotifier,
    ExperimentControlProcess,
    ExperimentControlReceipt,
    LaunchExperimentCommand,
    LaunchExperimentHandler,
    PauseExperimentCommand,
    PauseExperimentHandler,
    ResumeExperimentCommand,
    ResumeExperimentHandler,
    RetryExperimentFoldCommand,
    RetryExperimentFoldHandler,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPlanningProcess,
    ExperimentPlanningRequest,
)

NOW = datetime(2026, 7, 22, 9, 30, tzinfo=UTC)


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


@dataclass(frozen=True, slots=True)
class _ReplayAwareControlReceipt:
    experiment_id: str
    status: str
    desired_state: str
    revision: int
    occurred_at: datetime
    live_run_ids: tuple[str, ...]
    replayed: bool = field(compare=False, repr=False)


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


def _control_receipt(
    *,
    status: str,
    desired_state: str,
    revision: int = 8,
    live_run_ids: tuple[str, ...] = (),
) -> ExperimentControlReceipt:
    return ExperimentControlReceipt(
        experiment_id="experiment-1",
        status=status,
        desired_state=desired_state,
        revision=revision,
        occurred_at=NOW,
        live_run_ids=live_run_ids,
    )


class _ControlProcessDouble:
    def __init__(
        self,
        *,
        receipts: dict[str, ExperimentControlReceipt],
        timeline: list[tuple[object, ...]],
        error: AppProcessError | None = None,
    ) -> None:
        self._receipts = receipts
        self._timeline = timeline
        self._error = error

    def _result(self, action: str, *values: object) -> ExperimentControlReceipt:
        self._timeline.append(("process", action, *values))
        if self._error is not None:
            raise self._error
        return self._receipts[action]

    def pause(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        return self._result(
            "pause",
            experiment_id,
            expected_revision,
            occurred_at,
        )

    def cancel(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        return self._result(
            "cancel",
            experiment_id,
            expected_revision,
            occurred_at,
        )

    def resume(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        return self._result(
            "resume",
            experiment_id,
            expected_revision,
            occurred_at,
        )

    def retry_fold(
        self,
        *,
        experiment_id: str,
        candidate_id: str,
        fold_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        return self._result(
            "retry_fold",
            experiment_id,
            candidate_id,
            fold_id,
            expected_revision,
            occurred_at,
        )


class _ControlNotifierDouble:
    def __init__(
        self,
        *,
        timeline: list[tuple[object, ...]],
        error: Exception | None = None,
    ) -> None:
        self._timeline = timeline
        self._error = error

    def notify_run_stop(
        self,
        *,
        experiment_id: str,
        run_id: str,
        desired_state: str,
        occurred_at: datetime,
    ) -> None:
        self._timeline.append(
            (
                "notify_run_stop",
                experiment_id,
                run_id,
                desired_state,
                occurred_at,
            ),
        )
        if self._error is not None:
            raise self._error

    def notify_scheduler(
        self,
        *,
        experiment_id: str,
        action: str,
        occurred_at: datetime,
    ) -> None:
        self._timeline.append(
            ("notify_scheduler", experiment_id, action, occurred_at),
        )
        if self._error is not None:
            raise self._error


@pytest.mark.parametrize(
    ("action", "handler_type", "command", "status", "desired_state"),
    [
        (
            "pause",
            PauseExperimentHandler,
            PauseExperimentCommand("experiment-1", 7, NOW),
            "pause_requested",
            "pause",
        ),
        (
            "cancel",
            CancelExperimentHandler,
            CancelExperimentCommand("experiment-1", 7, NOW),
            "cancel_requested",
            "cancel",
        ),
    ],
)
def test_pause_and_cancel_persist_before_notifying_exact_live_runs(
    action: str,
    handler_type: type[PauseExperimentHandler] | type[CancelExperimentHandler],
    command: PauseExperimentCommand | CancelExperimentCommand,
    status: str,
    desired_state: str,
) -> None:
    timeline: list[tuple[object, ...]] = []
    receipt = _control_receipt(
        status=status,
        desired_state=desired_state,
        live_run_ids=("run-2", "run-1"),
    )
    process = _ControlProcessDouble(receipts={action: receipt}, timeline=timeline)
    notifier = _ControlNotifierDouble(timeline=timeline)
    handler = handler_type(
        process=cast("ExperimentControlProcess", process),
        notifier=cast("ExperimentControlNotifier", notifier),
    )

    result = handler.handle(command)

    assert result is receipt
    assert timeline == [
        ("process", action, "experiment-1", 7, NOW),
        (
            "notify_run_stop",
            "experiment-1",
            "run-2",
            desired_state,
            NOW,
        ),
        (
            "notify_run_stop",
            "experiment-1",
            "run-1",
            desired_state,
            NOW,
        ),
    ]


def test_exact_control_replay_does_not_repeat_post_commit_notification() -> None:
    timeline: list[tuple[object, ...]] = []
    receipts = iter(
        (
            _ReplayAwareControlReceipt(
                "experiment-1",
                "pause_requested",
                "pause",
                8,
                NOW,
                ("run-1",),
                False,
            ),
            _ReplayAwareControlReceipt(
                "experiment-1",
                "pause_requested",
                "pause",
                8,
                NOW,
                ("run-1",),
                True,
            ),
        )
    )

    class ReplayProcess:
        def pause(self, **values: object) -> _ReplayAwareControlReceipt:
            timeline.append(("process", values))
            return next(receipts)

    handler = PauseExperimentHandler(
        process=cast("ExperimentControlProcess", ReplayProcess()),
        notifier=cast(
            "ExperimentControlNotifier",
            _ControlNotifierDouble(timeline=timeline),
        ),
    )
    command = PauseExperimentCommand("experiment-1", 7, NOW)

    first = handler.handle(command)
    replay = handler.handle(command)

    assert first == replay
    assert [item for item in timeline if item[0] == "notify_run_stop"] == [
        (
            "notify_run_stop",
            "experiment-1",
            "run-1",
            "pause",
            NOW,
        )
    ]


@pytest.mark.parametrize(
    ("handler_type", "command", "status", "desired_state", "command_name"),
    [
        (
            PauseExperimentHandler,
            PauseExperimentCommand("experiment-1", 7, NOW),
            "pause_requested",
            "pause",
            "pause_experiment",
        ),
        (
            CancelExperimentHandler,
            CancelExperimentCommand("experiment-1", 7, NOW),
            "cancel_requested",
            "cancel",
            "cancel_experiment",
        ),
    ],
)
def test_stop_notification_failure_preserves_durable_receipt_without_retry(
    handler_type: type[PauseExperimentHandler] | type[CancelExperimentHandler],
    command: PauseExperimentCommand | CancelExperimentCommand,
    status: str,
    desired_state: str,
    command_name: str,
) -> None:
    timeline: list[tuple[object, ...]] = []
    receipt = _control_receipt(
        status=status,
        desired_state=desired_state,
        live_run_ids=("run-1", "run-2"),
    )
    process = _ControlProcessDouble(
        receipts={desired_state: receipt},
        timeline=timeline,
    )
    notification_error = RuntimeError("transport unavailable")
    notifier = _ControlNotifierDouble(
        timeline=timeline,
        error=notification_error,
    )
    handler = handler_type(
        process=cast("ExperimentControlProcess", process),
        notifier=cast("ExperimentControlNotifier", notifier),
    )

    with pytest.raises(AppCommandError) as exc_info:
        handler.handle(command)

    assert timeline == [
        ("process", desired_state, "experiment-1", 7, NOW),
        (
            "notify_run_stop",
            "experiment-1",
            "run-1",
            desired_state,
            NOW,
        ),
    ]
    assert exc_info.value.details == {
        "command": command_name,
        "notification": "stop_live_run",
        "notification_target": "run-1",
        "error_type": "RuntimeError",
        "experiment_id": "experiment-1",
        "status": status,
        "desired_state": desired_state,
        "revision": 8,
    }
    assert exc_info.value.__cause__ is notification_error


def test_resume_persists_then_notifies_scheduler_without_child_run() -> None:
    timeline: list[tuple[object, ...]] = []
    receipt = _control_receipt(status="queued", desired_state="run", revision=9)
    process = _ControlProcessDouble(receipts={"resume": receipt}, timeline=timeline)
    notifier = _ControlNotifierDouble(timeline=timeline)
    handler = ResumeExperimentHandler(
        process=cast("ExperimentControlProcess", process),
        notifier=cast("ExperimentControlNotifier", notifier),
    )

    result = handler.handle(ResumeExperimentCommand("experiment-1", 8, NOW))

    assert result is receipt
    assert timeline == [
        ("process", "resume", "experiment-1", 8, NOW),
        ("notify_scheduler", "experiment-1", "resume", NOW),
    ]


def test_retry_fold_persists_then_notifies_scheduler_without_child_run() -> None:
    timeline: list[tuple[object, ...]] = []
    receipt = _control_receipt(status="running", desired_state="run", revision=12)
    process = _ControlProcessDouble(
        receipts={"retry_fold": receipt},
        timeline=timeline,
    )
    notifier = _ControlNotifierDouble(timeline=timeline)
    handler = RetryExperimentFoldHandler(
        process=cast("ExperimentControlProcess", process),
        notifier=cast("ExperimentControlNotifier", notifier),
    )

    result = handler.handle(
        RetryExperimentFoldCommand(
            experiment_id="experiment-1",
            candidate_id="candidate-2",
            fold_id="fold-3",
            expected_revision=11,
            occurred_at=NOW,
        ),
    )

    assert result is receipt
    assert timeline == [
        (
            "process",
            "retry_fold",
            "experiment-1",
            "candidate-2",
            "fold-3",
            11,
            NOW,
        ),
        ("notify_scheduler", "experiment-1", "retry_fold", NOW),
    ]


def test_scheduler_notification_failure_preserves_durable_receipt() -> None:
    timeline: list[tuple[object, ...]] = []
    receipt = _control_receipt(status="queued", desired_state="run", revision=9)
    process = _ControlProcessDouble(receipts={"resume": receipt}, timeline=timeline)
    notification_error = RuntimeError("scheduler wake failed")
    notifier = _ControlNotifierDouble(
        timeline=timeline,
        error=notification_error,
    )
    handler = ResumeExperimentHandler(
        process=cast("ExperimentControlProcess", process),
        notifier=cast("ExperimentControlNotifier", notifier),
    )

    with pytest.raises(AppCommandError) as exc_info:
        handler.handle(ResumeExperimentCommand("experiment-1", 8, NOW))

    assert timeline == [
        ("process", "resume", "experiment-1", 8, NOW),
        ("notify_scheduler", "experiment-1", "resume", NOW),
    ]
    assert exc_info.value.details == {
        "command": "resume_experiment",
        "notification": "scheduler_action",
        "notification_target": "resume",
        "error_type": "RuntimeError",
        "experiment_id": "experiment-1",
        "status": "queued",
        "desired_state": "run",
        "revision": 9,
    }


@pytest.mark.parametrize(
    ("handler_type", "command", "process_action", "command_name"),
    [
        (
            PauseExperimentHandler,
            PauseExperimentCommand("experiment-1", 7, NOW),
            "pause",
            "pause_experiment",
        ),
        (
            CancelExperimentHandler,
            CancelExperimentCommand("experiment-1", 7, NOW),
            "cancel",
            "cancel_experiment",
        ),
        (
            ResumeExperimentHandler,
            ResumeExperimentCommand("experiment-1", 7, NOW),
            "resume",
            "resume_experiment",
        ),
        (
            RetryExperimentFoldHandler,
            RetryExperimentFoldCommand(
                "experiment-1",
                "candidate-2",
                "fold-3",
                7,
                NOW,
            ),
            "retry_fold",
            "retry_experiment_fold",
        ),
    ],
)
def test_control_handlers_translate_process_errors_without_notification(
    handler_type: type[
        PauseExperimentHandler
        | CancelExperimentHandler
        | ResumeExperimentHandler
        | RetryExperimentFoldHandler
    ],
    command: (
        PauseExperimentCommand
        | CancelExperimentCommand
        | ResumeExperimentCommand
        | RetryExperimentFoldCommand
    ),
    process_action: str,
    command_name: str,
) -> None:
    timeline: list[tuple[object, ...]] = []
    process_error = AppProcessError(
        "control revision is stale",
        details={"code": "EXPERIMENT_CONFLICT", "reason": "stale_revision"},
    )
    process = _ControlProcessDouble(
        receipts={},
        timeline=timeline,
        error=process_error,
    )
    notifier = _ControlNotifierDouble(timeline=timeline)
    handler = handler_type(
        process=cast("ExperimentControlProcess", process),
        notifier=cast("ExperimentControlNotifier", notifier),
    )

    with pytest.raises(AppCommandError) as exc_info:
        handler.handle(command)

    assert len(timeline) == 1
    assert timeline[0][0:2] == ("process", process_action)
    assert exc_info.value.details == {
        "code": "EXPERIMENT_CONFLICT",
        "reason": "stale_revision",
        "command": command_name,
        "experiment_id": "experiment-1",
    }
    assert exc_info.value.__cause__ is process_error
