"""Fail-closed deterministic Agent Run transitions."""

from __future__ import annotations

from ditto_agent.contracts.runtime import RunStatus

_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.COMPLETED,
            RunStatus.WAITING_APPROVAL,
            RunStatus.PAUSED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.WAITING_APPROVAL: frozenset({RunStatus.RUNNING}),
    RunStatus.PAUSED: frozenset({RunStatus.RUNNING}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class InvalidRunTransition(ValueError):
    """Raised when a host attempts an undeclared or duplicate transition."""


def transition_run(source: RunStatus, target: RunStatus) -> RunStatus:
    """Return the declared target or reject the transition without mutation."""
    if target not in _TRANSITIONS[source]:
        raise InvalidRunTransition(
            f"illegal run transition: {source.value} -> {target.value}"
        )
    return target


__all__ = ["InvalidRunTransition", "transition_run"]
