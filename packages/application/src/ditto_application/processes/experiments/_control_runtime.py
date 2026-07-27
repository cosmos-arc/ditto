"""
R3 control-only runtime wiring: best-effort notifier + placeholder factory.

The experiment control routes (pause/cancel/resume/retry-fold) drive
``ExperimentExecutionCoordinator`` as an ``ExperimentControlProcess``. They
persist operator intent via durable store CAS and never dispatch first or
successor attempts — that is the tick dispatch path, which requires the
content-addressed execution bundle (Task 9/13) not yet wired. This module
provides two additive production implementations used only by the control DI:

* ``LoggingExperimentControlNotifier`` — best-effort post-commit notification.
  In the R3 single-machine durable-tick model the worker already polls durable
  ``desired_state`` via ``poll_execution_directive``, and the scheduler is an
  explicit prefect flow, so the notifier only logs. Durable state plus the
  explicit tick are the correctness boundary; notification failure never
  corrupts truth.
* ``ControlOnlyFirstAttemptFactory`` — placeholder ``FirstAttemptFactory`` that
  fails loudly if ever invoked. Replace with
  ``ExecutionBundleFirstAttemptFactory`` once the execution bundle resolver is
  wired (tick dispatch path).

Neither changes coordinator control semantics; both exist only so a production
coordinator can be constructed for control-route DI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ditto_analysis.experiments import (
    AttemptView,
    BacktestRunId,
    ExperimentId,
    FoldView,
)
from ditto_platform.foundation import logger

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments._coordinator_recovery import (
    ExperimentRecoveryOrchestrator,
)
from ditto_application.processes.experiments.lease_authority import LeaseAuthority
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
    FirstAttempt,
    QueuedAttempt,
)

__all__ = [
    "CONTROL_COORDINATOR_LEASE_DURATION",
    "CONTROL_COORDINATOR_OWNER_TOKEN",
    "CONTROL_ONLY_FACTORY_CODE",
    "CONTROL_ONLY_FACTORY_REASON",
    "ControlOnlyFirstAttemptFactory",
    "LoggingExperimentControlNotifier",
    "RetryFoldControlRequest",
    "retry_fold_under_transient_lease",
]

CONTROL_ONLY_FACTORY_CODE = "CONTROL_ONLY_FACTORY"
CONTROL_ONLY_FACTORY_REASON = "first_attempt_factory_not_wired"

CONTROL_COORDINATOR_OWNER_TOKEN = "ditto-research-scheduler"  # noqa: S105
CONTROL_COORDINATOR_LEASE_DURATION = timedelta(minutes=5)


class LoggingExperimentControlNotifier:
    """Best-effort post-commit notifier for the R3 single-machine tick model."""

    def notify_run_stop(
        self,
        *,
        experiment_id: str,
        run_id: str,
        desired_state: str,
        occurred_at: datetime,
    ) -> None:
        """Log a cooperative stop request; the worker polls durable desired_state."""
        logger.info(
            "experiment control requested cooperative run stop",
            experiment_id=experiment_id,
            run_id=run_id,
            desired_state=desired_state,
            occurred_at=occurred_at.isoformat(),
        )

    def notify_scheduler(
        self,
        *,
        experiment_id: str,
        action: str,
        occurred_at: datetime,
    ) -> None:
        """Log a scheduler wake request; the tick flow consumes durable intent."""
        logger.info(
            "experiment control requested scheduler wake",
            experiment_id=experiment_id,
            action=action,
            occurred_at=occurred_at.isoformat(),
        )


class ControlOnlyFirstAttemptFactory:
    """
    Placeholder factory for control-only coordinator wiring.

    Control operations persist intent via store CAS without manufacturing
    attempt identity. This factory raises if ever invoked, which happens only
    on the tick dispatch path (not wired in R3 control-only wiring). Replace
    with ``ExecutionBundleFirstAttemptFactory`` once the execution bundle
    resolver (``ResearchExecutionSemanticsResolver``) is assembled.
    """

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        """Fail loudly; first attempts require the execution bundle resolver."""
        raise _factory_error()

    def create_successor(
        self,
        fold: FoldView,
        parent: AttemptView,
        *,
        resume_from_run_id: BacktestRunId | None,
        occurred_at: datetime,
    ) -> QueuedAttempt:
        """Fail loudly; successor attempts require the execution bundle resolver."""
        raise _factory_error()


def _factory_error() -> AppProcessError:
    """Build the stable typed error for any placeholder factory invocation."""
    return AppProcessError(
        "control-only coordinator cannot manufacture attempts",
        details={
            "code": CONTROL_ONLY_FACTORY_CODE,
            "reason": CONTROL_ONLY_FACTORY_REASON,
        },
    )


@dataclass(frozen=True, slots=True)
class RetryFoldControlRequest:
    """One operator-initiated terminal fold retry request (control route)."""

    experiment_id: str
    candidate_id: str
    fold_id: str
    expected_revision: int
    occurred_at: datetime


def retry_fold_under_transient_lease(
    *,
    store: ExperimentSchedulerStoreProtocol,
    authority: LeaseAuthority,
    recovery: ExperimentRecoveryOrchestrator,
    request: RetryFoldControlRequest,
) -> ExperimentControlReceipt:
    """
    Retry one terminal fold via a transient scheduler lease (control route).

    Control routes run outside the tick loop, so this acquires a transient
    scheduler lease, executes the fenced retry, and releases. The durable store
    CAS (``stale_fold_revision`` + lease fence) is the correctness boundary;
    in R3 single-machine wiring there is no concurrent tick. If the slot is
    currently leased by another authority the request fails closed with
    ``LEASE_LOST``. A lease already held by this coordinator remains owned by
    its scheduler lifecycle and is never released by this control operation.
    """
    slot = store.get_scheduler_slot()
    return authority.execute_operator_under_transient_lease(
        ExperimentId(request.experiment_id),
        expected_revision=slot.revision,
        operation=lambda lease, now_epoch_us: recovery.retry_fold(
            experiment_id=request.experiment_id,
            candidate_id=request.candidate_id,
            fold_id=request.fold_id,
            expected_revision=request.expected_revision,
            occurred_at=request.occurred_at,
            lease=lease,
            now_epoch_us=now_epoch_us(),
        ),
    )
