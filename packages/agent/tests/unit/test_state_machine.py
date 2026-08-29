from __future__ import annotations

import pytest
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.runtime.state_machine import InvalidRunTransition, transition_run


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.QUEUED, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
        (RunStatus.RUNNING, RunStatus.WAITING_APPROVAL),
        (RunStatus.WAITING_APPROVAL, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.PAUSED),
        (RunStatus.PAUSED, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
    ],
)
def test_declared_run_transitions_are_allowed(
    source: RunStatus, target: RunStatus
) -> None:
    assert transition_run(source, target) is target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RunStatus.QUEUED, RunStatus.COMPLETED),
        (RunStatus.WAITING_APPROVAL, RunStatus.COMPLETED),
        (RunStatus.PAUSED, RunStatus.COMPLETED),
        (RunStatus.COMPLETED, RunStatus.RUNNING),
        (RunStatus.FAILED, RunStatus.RUNNING),
        (RunStatus.CANCELLED, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.RUNNING),
    ],
)
def test_illegal_duplicate_and_terminal_transitions_fail_closed(
    source: RunStatus, target: RunStatus
) -> None:
    with pytest.raises(InvalidRunTransition, match=f"{source.value}.*{target.value}"):
        transition_run(source, target)
