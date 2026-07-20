"""Command boundary for confirmed research experiment launches."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPlanningProcess,
    ExperimentPlanningRequest,
)

__all__ = ["LaunchExperimentCommand", "LaunchExperimentHandler"]


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
