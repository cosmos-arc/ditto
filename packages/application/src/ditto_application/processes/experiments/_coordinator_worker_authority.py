"""Worker-facing lease operations shared by the experiment coordinator."""

from __future__ import annotations

from datetime import datetime

from ditto_application.processes.experiments.lease_authority import (
    LeaseAuthority,
    RenewedLeaseOperation,
    require_utc_event_time,
)
from ditto_application.processes.experiments.scheduler_store import SchedulerLease

__all__ = ["WorkerLeaseAuthorityCoordinator"]


class WorkerLeaseAuthorityCoordinator:
    """Expose only renewed worker authority without leaking its owner object."""

    _authority: LeaseAuthority

    def renew_lease(self, *, occurred_at: datetime | None = None) -> SchedulerLease:
        """Renew from the authority clock; retain worker-call compatibility."""
        if occurred_at is not None:
            require_utc_event_time(occurred_at)
        return self._authority.renew()

    def publish_attempt_artifact[ResultT](
        self,
        operation: RenewedLeaseOperation[ResultT],
    ) -> ResultT:
        """Synchronously publish one attempt artifact under a renewed fence."""
        return self._authority.execute_recoverable_under_renewed_lease(operation)
