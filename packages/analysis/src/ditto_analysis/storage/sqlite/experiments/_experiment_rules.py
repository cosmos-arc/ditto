"""Central experiment lifecycle ownership and intent rules."""

from __future__ import annotations

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import (
    ExperimentDesiredState,
    ExperimentStatus,
)

ACTIVE_EXPERIMENT_INTENT = {
    ExperimentStatus.QUEUED: ExperimentDesiredState.RUN,
    ExperimentStatus.RUNNING: ExperimentDesiredState.RUN,
    ExperimentStatus.PAUSE_REQUESTED: ExperimentDesiredState.PAUSE,
    ExperimentStatus.PAUSED: ExperimentDesiredState.PAUSE,
    ExperimentStatus.CANCEL_REQUESTED: ExperimentDesiredState.CANCEL,
}
TERMINAL_EXPERIMENT_STATUSES = frozenset(
    {
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.COMPLETED_WITH_FAILURES,
        ExperimentStatus.FAILED,
    }
)

_OPERATOR_TRANSITION_INTENT = {
    (ExperimentStatus.DRAFT, ExperimentStatus.BLOCKED): (
        ExperimentDesiredState.RUN,
        ExperimentDesiredState.RUN,
    ),
    (ExperimentStatus.QUEUED, ExperimentStatus.CANCEL_REQUESTED): (
        ExperimentDesiredState.RUN,
        ExperimentDesiredState.CANCEL,
    ),
    (ExperimentStatus.RUNNING, ExperimentStatus.PAUSE_REQUESTED): (
        ExperimentDesiredState.RUN,
        ExperimentDesiredState.PAUSE,
    ),
    (ExperimentStatus.RUNNING, ExperimentStatus.CANCEL_REQUESTED): (
        ExperimentDesiredState.RUN,
        ExperimentDesiredState.CANCEL,
    ),
    (ExperimentStatus.PAUSED, ExperimentStatus.QUEUED): (
        ExperimentDesiredState.PAUSE,
        ExperimentDesiredState.RUN,
    ),
    (ExperimentStatus.PAUSED, ExperimentStatus.CANCEL_REQUESTED): (
        ExperimentDesiredState.PAUSE,
        ExperimentDesiredState.CANCEL,
    ),
}

_SCHEDULED_TRANSITION_INTENT = {
    (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING): ExperimentDesiredState.RUN,
    (
        ExperimentStatus.PAUSE_REQUESTED,
        ExperimentStatus.PAUSED,
    ): ExperimentDesiredState.PAUSE,
    (
        ExperimentStatus.CANCEL_REQUESTED,
        ExperimentStatus.CANCELLED,
    ): ExperimentDesiredState.CANCEL,
    (ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED): ExperimentDesiredState.RUN,
    (
        ExperimentStatus.RUNNING,
        ExperimentStatus.COMPLETED_WITH_FAILURES,
    ): ExperimentDesiredState.RUN,
    (ExperimentStatus.RUNNING, ExperimentStatus.FAILED): ExperimentDesiredState.RUN,
}


def validate_expected_desired_state(
    status: ExperimentStatus,
    actual: ExperimentDesiredState,
    expected: ExperimentDesiredState,
) -> None:
    """Reject a projection whose durable intent disagrees with its operation."""
    if actual is not expected:
        raise ExperimentSpecError(
            "experiment desired state disagrees with its lifecycle operation",
            details={
                "reason_code": "experiment_desired_state_mismatch",
                "status": status.value,
                "desired_state": actual.value,
                "expected_desired_state": expected.value,
            },
        )


def validate_operator_experiment_transition(
    current_status: ExperimentStatus,
    current_desired_state: ExperimentDesiredState,
    target_status: ExperimentStatus,
    target_desired_state: ExperimentDesiredState,
) -> None:
    """Own operator edges and require their exact source and target intent."""
    policy = _OPERATOR_TRANSITION_INTENT.get((current_status, target_status))
    if policy is None:
        raise ExperimentSpecError(
            "scheduler-owned experiment transition requires a lease fence",
            details={"reason_code": "scheduler_transition_requires_fence"},
        )
    expected_source, expected_target = policy
    validate_expected_desired_state(
        current_status,
        current_desired_state,
        expected_source,
    )
    validate_expected_desired_state(
        target_status,
        target_desired_state,
        expected_target,
    )


def validate_scheduled_experiment_transition(
    current_status: ExperimentStatus,
    target_status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
) -> None:
    """Own scheduler edges without allowing the scheduler to forge intent."""
    expected = _SCHEDULED_TRANSITION_INTENT.get((current_status, target_status))
    if expected is None:
        raise ExperimentSpecError(
            "operator-owned transition requires the operator command",
            details={"reason_code": "operator_transition_requires_operator_command"},
        )
    validate_expected_desired_state(current_status, desired_state, expected)
