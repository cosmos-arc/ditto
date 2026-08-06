"""
Execution lease heartbeat extracted from the research fold worker.

Keeps :mod:`worker` under its size budget by owning the background thread
that renews durable execution authority while a blocking fold call is in
flight. Mirrors the extraction pattern of :mod:`_worker_attestation` and
:mod:`_worker_contract`: a leaf module with its own typed error helper so it
never has to import worker internals (which would form a cycle).
"""

from __future__ import annotations

from threading import Event, Thread

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.lease_authority import (
    ResearchExecutionControl,
)

__all__ = ["EXECUTION_HEARTBEAT_INTERVAL_SECONDS", "ExecutionLeaseHeartbeat"]

EXECUTION_HEARTBEAT_INTERVAL_SECONDS = 30.0


def _heartbeat_error(reason: str) -> AppProcessError:
    return AppProcessError(
        "research experiment worker contract is invalid",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
        },
    )


class ExecutionLeaseHeartbeat:
    """Renew durable execution authority while a fold call is blocking."""

    def __init__(
        self,
        control: ResearchExecutionControl,
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise _heartbeat_error("heartbeat_interval_must_be_positive")
        self._control = control
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._thread = Thread(
            target=self._run,
            name="ditto-research-lease-heartbeat",
            daemon=True,
        )

    def __enter__(self) -> ExecutionLeaseHeartbeat:
        self._thread.start()
        return self

    def __exit__(self, *_error: object) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            if self._control.should_stop():
                return
