"""Worker-facing lease operations shared by the experiment coordinator."""

from __future__ import annotations

from ditto_application.processes.experiments.lease_authority import (
    LeaseAuthority,
    LeaseOperation,
)
from ditto_application.processes.experiments.scheduler_store import SchedulerLease

__all__ = ["WorkerLeaseAuthorityCoordinator"]


class WorkerLeaseAuthorityCoordinator:
    """Expose worker publication authority without leaking its owner object."""

    _authority: LeaseAuthority

    def current_lease(self) -> SchedulerLease:
        """Return the current claim for read-only fence inspection."""
        return self._authority.require_current_lease()

    def publish_attempt_artifact[ResultT](
        self,
        operation: LeaseOperation[ResultT],
    ) -> ResultT:
        """Synchronously publish one attempt artifact under the current fence."""
        return self._authority.execute_recoverable_publication(operation)
