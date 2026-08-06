"""Operator-control entrypoints kept separate from scheduler orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ditto_application.mutation_idempotency import MutationIdempotency
from ditto_application.processes.experiments._control_runtime import (
    retry_fold_under_transient_lease,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
    RetryFoldControlRequest,
)
from ditto_application.processes.experiments._coordinator_recovery import (
    ExperimentRecoveryOrchestrator,
)
from ditto_application.processes.experiments._mutation_receipts import (
    replay_control_receipt,
)
from ditto_application.processes.experiments.lease_authority import (
    LeaseAuthority,
    require_utc_event_time,
    run_unfenced_scheduler_operation,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)


class OperatorControlOperation(Protocol):
    """Callable shape shared by recovery pause, cancel, and resume."""

    def __call__(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt: ...


def persist_experiment_control(
    operation: OperatorControlOperation,
    *,
    experiment_id: str,
    expected_revision: int,
    occurred_at: datetime,
    idempotency: MutationIdempotency | None,
) -> ExperimentControlReceipt:
    """Validate time and execute one pause, cancel, or resume CAS."""
    require_utc_event_time(occurred_at)
    return run_unfenced_scheduler_operation(
        lambda: operation(
            experiment_id=experiment_id,
            expected_revision=expected_revision,
            occurred_at=occurred_at,
            idempotency=idempotency,
        )
    )


def retry_fold_control(
    *,
    store: ExperimentSchedulerStoreProtocol,
    authority: LeaseAuthority,
    recovery: ExperimentRecoveryOrchestrator,
    request: RetryFoldControlRequest,
) -> ExperimentControlReceipt:
    """Replay before acquiring the transient lease for one terminal retry."""
    require_utc_event_time(request.occurred_at)
    replay = replay_control_receipt(
        store,
        request.idempotency,
        experiment_id=request.experiment_id,
        candidate_id=request.candidate_id,
        fold_id=request.fold_id,
    )
    if replay is not None:
        return replay
    return retry_fold_under_transient_lease(
        store=store,
        authority=authority,
        recovery=recovery,
        request=request,
    )


class ExperimentControlCoordinatorMixin:
    """Public control facade shared by the full execution coordinator."""

    _store: ExperimentSchedulerStoreProtocol
    _authority: LeaseAuthority
    _recovery: ExperimentRecoveryOrchestrator

    def pause(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt:
        """Persist pause intent before any child notification occurs."""
        return persist_experiment_control(
            self._recovery.pause,
            experiment_id=experiment_id,
            expected_revision=expected_revision,
            occurred_at=occurred_at,
            idempotency=idempotency,
        )

    def cancel(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt:
        """Persist cancellation intent before any child notification occurs."""
        return persist_experiment_control(
            self._recovery.cancel,
            experiment_id=experiment_id,
            expected_revision=expected_revision,
            occurred_at=occurred_at,
            idempotency=idempotency,
        )

    def resume(
        self,
        *,
        experiment_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt:
        """Persist RUN intent without constructing a successor attempt early."""
        return persist_experiment_control(
            self._recovery.resume,
            experiment_id=experiment_id,
            expected_revision=expected_revision,
            occurred_at=occurred_at,
            idempotency=idempotency,
        )

    def retry_fold(
        self,
        *,
        experiment_id: str,
        candidate_id: str,
        fold_id: str,
        expected_revision: int,
        occurred_at: datetime,
        idempotency: MutationIdempotency | None = None,
    ) -> ExperimentControlReceipt:
        """Requeue one eligible terminal fold via a transient control-route lease."""
        return retry_fold_control(
            store=self._store,
            authority=self._authority,
            recovery=self._recovery,
            request=RetryFoldControlRequest(
                experiment_id=experiment_id,
                candidate_id=candidate_id,
                fold_id=fold_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                idempotency=idempotency,
            ),
        )


__all__ = [
    "ExperimentControlCoordinatorMixin",
    "persist_experiment_control",
    "retry_fold_control",
]
