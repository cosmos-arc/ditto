"""Command boundary for durable research experiment control actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPlanningProcess,
    ExperimentPlanningRequest,
)

__all__ = [
    "CancelExperimentCommand",
    "CancelExperimentHandler",
    "ExperimentControlNotifier",
    "ExperimentControlProcess",
    "ExperimentControlReceipt",
    "LaunchExperimentCommand",
    "LaunchExperimentHandler",
    "PauseExperimentCommand",
    "PauseExperimentHandler",
    "ResumeExperimentCommand",
    "ResumeExperimentHandler",
    "RetryExperimentFoldCommand",
    "RetryExperimentFoldHandler",
]


@dataclass(frozen=True, slots=True)
class LaunchExperimentCommand:
    """Launch one exact planning request after operator hash confirmation."""

    request: ExperimentPlanningRequest
    confirmed_plan_hash: str


class LaunchExperimentHandler:
    """Delegate durable launch orchestration to ``ExperimentPlanningProcess``."""

    def __init__(self, process: ExperimentPlanningProcess) -> None:
        self._process = process

    def handle(self, command: LaunchExperimentCommand) -> ExperimentLaunchReceipt:
        """Launch the confirmed plan and preserve typed failures at CQRS boundary."""
        try:
            return self._process.launch(
                command.request,
                confirmed_plan_hash=command.confirmed_plan_hash,
            )
        except AppProcessError as exc:
            details = dict(exc.details)
            details.update(
                {
                    "command": "launch_experiment",
                    "experiment_id": command.request.experiment_id,
                },
            )
            raise AppCommandError(str(exc), details=details) from exc


@dataclass(frozen=True, slots=True)
class PauseExperimentCommand:
    """Request a revision-fenced cooperative experiment pause."""

    experiment_id: str
    expected_revision: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class CancelExperimentCommand:
    """Request a revision-fenced terminal experiment cancellation."""

    experiment_id: str
    expected_revision: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ResumeExperimentCommand:
    """Request a revision-fenced resume of one paused experiment."""

    experiment_id: str
    expected_revision: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class RetryExperimentFoldCommand:
    """Request a revision-fenced successor attempt for one exact fold."""

    experiment_id: str
    candidate_id: str
    fold_id: str
    expected_revision: int
    occurred_at: datetime


class ExperimentControlProcess(Protocol):
    """Durable process boundary owning every experiment control CAS."""

    def pause(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Persist pause intent and return committed server truth."""
        ...

    def cancel(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Persist cancel intent and return committed server truth."""
        ...

    def resume(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Persist run intent for a paused experiment."""
        ...

    def retry_fold(
        self,
        *,
        experiment_id: str,
        candidate_id: str,
        fold_id: str,
        expected_revision: int,
        occurred_at: datetime,
    ) -> ExperimentControlReceipt:
        """Persist one successor-attempt request without creating a child run."""
        ...


class ExperimentControlNotifier(Protocol):
    """Post-commit notification boundary with no durable mutation authority."""

    def notify_run_stop(
        self,
        *,
        experiment_id: str,
        run_id: str,
        desired_state: str,
        occurred_at: datetime,
    ) -> None:
        """Ask one already-persisted live child run to stop cooperatively."""
        ...

    def notify_scheduler(
        self,
        *,
        experiment_id: str,
        action: str,
        occurred_at: datetime,
    ) -> None:
        """Wake the scheduler for a committed resume or retry action."""
        ...


class _ExperimentControlHandler:
    """Shared post-CAS notification mechanics for concrete command handlers."""

    def __init__(
        self,
        *,
        process: ExperimentControlProcess,
        notifier: ExperimentControlNotifier,
    ) -> None:
        self._process = process
        self._notifier = notifier

    def _notify_live_runs(
        self,
        receipt: ExperimentControlReceipt,
        *,
        command_name: str,
    ) -> None:
        for run_id in receipt.live_run_ids:
            try:
                self._notifier.notify_run_stop(
                    experiment_id=receipt.experiment_id,
                    run_id=run_id,
                    desired_state=receipt.desired_state,
                    occurred_at=receipt.occurred_at,
                )
            except Exception as exc:
                raise _notification_error(
                    exc,
                    receipt,
                    command_name=command_name,
                    notification="stop_live_run",
                    notification_target=run_id,
                ) from exc

    def _notify_scheduler(
        self,
        receipt: ExperimentControlReceipt,
        *,
        command_name: str,
        action: str,
    ) -> None:
        try:
            self._notifier.notify_scheduler(
                experiment_id=receipt.experiment_id,
                action=action,
                occurred_at=receipt.occurred_at,
            )
        except Exception as exc:
            raise _notification_error(
                exc,
                receipt,
                command_name=command_name,
                notification="scheduler_action",
                notification_target=action,
            ) from exc


class PauseExperimentHandler(_ExperimentControlHandler):
    """Persist pause intent before notifying exact persisted live children."""

    def handle(self, command: PauseExperimentCommand) -> ExperimentControlReceipt:
        """Commit pause intent once, then notify each receipt-owned live run."""
        try:
            receipt = self._process.pause(
                experiment_id=command.experiment_id,
                expected_revision=command.expected_revision,
                occurred_at=command.occurred_at,
            )
        except AppProcessError as exc:
            raise _control_process_error(
                exc,
                command_name="pause_experiment",
                experiment_id=command.experiment_id,
            ) from exc
        self._notify_live_runs(receipt, command_name="pause_experiment")
        return receipt


class CancelExperimentHandler(_ExperimentControlHandler):
    """Persist cancel intent before notifying exact persisted live children."""

    def handle(self, command: CancelExperimentCommand) -> ExperimentControlReceipt:
        """Commit cancel intent once, then notify each receipt-owned live run."""
        try:
            receipt = self._process.cancel(
                experiment_id=command.experiment_id,
                expected_revision=command.expected_revision,
                occurred_at=command.occurred_at,
            )
        except AppProcessError as exc:
            raise _control_process_error(
                exc,
                command_name="cancel_experiment",
                experiment_id=command.experiment_id,
            ) from exc
        self._notify_live_runs(receipt, command_name="cancel_experiment")
        return receipt


class ResumeExperimentHandler(_ExperimentControlHandler):
    """Persist resume intent before waking the scheduler."""

    def handle(self, command: ResumeExperimentCommand) -> ExperimentControlReceipt:
        """Commit resume intent without manufacturing a child-run identity."""
        try:
            receipt = self._process.resume(
                experiment_id=command.experiment_id,
                expected_revision=command.expected_revision,
                occurred_at=command.occurred_at,
            )
        except AppProcessError as exc:
            raise _control_process_error(
                exc,
                command_name="resume_experiment",
                experiment_id=command.experiment_id,
            ) from exc
        self._notify_scheduler(
            receipt,
            command_name="resume_experiment",
            action="resume",
        )
        return receipt


class RetryExperimentFoldHandler(_ExperimentControlHandler):
    """Persist one fold retry request before waking the scheduler."""

    def handle(self, command: RetryExperimentFoldCommand) -> ExperimentControlReceipt:
        """Commit retry intent without manufacturing a successor child run."""
        try:
            receipt = self._process.retry_fold(
                experiment_id=command.experiment_id,
                candidate_id=command.candidate_id,
                fold_id=command.fold_id,
                expected_revision=command.expected_revision,
                occurred_at=command.occurred_at,
            )
        except AppProcessError as exc:
            raise _control_process_error(
                exc,
                command_name="retry_experiment_fold",
                experiment_id=command.experiment_id,
            ) from exc
        self._notify_scheduler(
            receipt,
            command_name="retry_experiment_fold",
            action="retry_fold",
        )
        return receipt


def _control_process_error(
    error: AppProcessError,
    *,
    command_name: str,
    experiment_id: str,
) -> AppCommandError:
    details = dict(error.details)
    details.update({"command": command_name, "experiment_id": experiment_id})
    return AppCommandError(str(error), details=details)


def _notification_error(
    error: Exception,
    receipt: ExperimentControlReceipt,
    *,
    command_name: str,
    notification: str,
    notification_target: str,
) -> AppCommandError:
    details = dict(error.details) if isinstance(error, AppProcessError) else {}
    details.update(
        {
            "command": command_name,
            "notification": notification,
            "notification_target": notification_target,
            "error_type": type(error).__name__,
            "experiment_id": receipt.experiment_id,
            "status": receipt.status,
            "desired_state": receipt.desired_state,
            "revision": receipt.revision,
        },
    )
    return AppCommandError(
        "experiment control was persisted but notification failed",
        details=details,
    )
