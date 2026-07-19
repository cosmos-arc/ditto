"""Unit tests for experiment observed-state transition validation."""

import pytest
from ditto_analysis.errors import ExperimentStateTransitionError
from ditto_analysis.experiments import ExperimentStatus, validate_status_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ExperimentStatus.DRAFT, ExperimentStatus.QUEUED),
        (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING),
        (ExperimentStatus.RUNNING, ExperimentStatus.PAUSE_REQUESTED),
        (ExperimentStatus.PAUSE_REQUESTED, ExperimentStatus.PAUSED),
        (ExperimentStatus.PAUSED, ExperimentStatus.QUEUED),
        (ExperimentStatus.QUEUED, ExperimentStatus.CANCEL_REQUESTED),
        (ExperimentStatus.RUNNING, ExperimentStatus.CANCEL_REQUESTED),
        (ExperimentStatus.PAUSED, ExperimentStatus.CANCEL_REQUESTED),
        (ExperimentStatus.CANCEL_REQUESTED, ExperimentStatus.CANCELLED),
        (ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED),
        (ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED_WITH_FAILURES),
    ],
)
def test_declared_state_transitions_are_legal(
    current: ExperimentStatus, target: ExperimentStatus
) -> None:
    assert validate_status_transition(current, target, attempt_started=True) is target


def test_draft_cannot_transition_directly_to_running() -> None:
    with pytest.raises(ExperimentStateTransitionError) as exc_info:
        validate_status_transition(
            ExperimentStatus.DRAFT,
            ExperimentStatus.RUNNING,
            attempt_started=False,
        )

    assert exc_info.value.details == {
        "reason_code": "illegal_experiment_state_transition",
        "current_status": "draft",
        "target_status": "running",
    }


def test_blocked_only_applies_before_attempt_when_precondition_is_repairable() -> None:
    assert (
        validate_status_transition(
            ExperimentStatus.DRAFT,
            ExperimentStatus.BLOCKED,
            attempt_started=False,
            precondition_repairable=True,
        )
        is ExperimentStatus.BLOCKED
    )
    for attempt_started, repairable in ((True, True), (False, False)):
        with pytest.raises(ExperimentStateTransitionError):
            validate_status_transition(
                ExperimentStatus.DRAFT,
                ExperimentStatus.BLOCKED,
                attempt_started=attempt_started,
                precondition_repairable=repairable,
            )


def test_failed_only_applies_after_attempt_started() -> None:
    assert (
        validate_status_transition(
            ExperimentStatus.RUNNING,
            ExperimentStatus.FAILED,
            attempt_started=True,
        )
        is ExperimentStatus.FAILED
    )
    with pytest.raises(ExperimentStateTransitionError):
        validate_status_transition(
            ExperimentStatus.RUNNING,
            ExperimentStatus.FAILED,
            attempt_started=False,
        )


def test_unknown_status_fails_closed_with_typed_error() -> None:
    with pytest.raises(ExperimentStateTransitionError) as exc_info:
        validate_status_transition("draft", "queued", attempt_started=False)

    assert exc_info.value.details["reason_code"] == "unknown_experiment_status"
