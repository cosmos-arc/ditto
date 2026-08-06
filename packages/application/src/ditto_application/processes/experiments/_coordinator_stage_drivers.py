"""
Stage-progression side-effect helpers extracted from the durable coordinator.

These helpers keep :mod:`coordinator` under its size budget by owning the
write-side loops that walk persisted folds while the coordinator drives the
tick loop. Each helper is a pure function over its store and snapshot inputs.

* :func:`drive_evidence_completion` closes the EVIDENCE stage by collecting the
  review packet and transitioning the experiment to ``COMPLETED``.
* :func:`cancel_failed_candidate_folds` cancels queued folds of failed
  candidates so the next dispatch skips them.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ditto_analysis.experiments import (
    ExperimentId,
    ExperimentStatus,
    SchedulerLease,
)

from ditto_application.processes.experiments._coordinator_contract import (
    SchedulerTickState,
)
from ditto_application.processes.experiments._coordinator_snapshot import (
    SnapshotVocabulary,
    candidate_failure_ids,
)
from ditto_application.processes.experiments.evidence_collector import (
    ExperimentEvidenceCollector,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStoreProtocol,
)

__all__ = ["cancel_failed_candidate_folds", "drive_evidence_completion"]


def drive_evidence_completion(
    *,
    collector: ExperimentEvidenceCollector | None,
    store: ExperimentSchedulerStoreProtocol,
    snapshot: ExperimentSchedulerSnapshot,
    lease: SchedulerLease,
    now_epoch_us: Callable[[], int],
    occurred_at: datetime,
    reload_snapshot: Callable[[ExperimentId], ExperimentSchedulerSnapshot],
) -> tuple[ExperimentSchedulerSnapshot, SchedulerTickState]:
    """
    Drive one EVIDENCE-stage tick toward the terminal ``COMPLETED`` status.

    Returns ``(snapshot, WAITING)`` without side effects when ``collector`` is
    ``None`` (test or degraded wiring). Otherwise the collector assembles and
    publishes the immutable review packet, the store transitions the experiment
    to ``COMPLETED`` under the lease fence, and the helper returns the reloaded
    snapshot paired with ``SchedulerTickState.COMPLETED``. Typed errors raised
    by the collector propagate to the coordinator tick for fail-fast handling;
    the transition is never attempted after a collector failure.
    """
    if collector is None:
        return snapshot, SchedulerTickState.WAITING
    collector.collect(
        snapshot.projection.record.experiment_id,
        lease_fence=lease.fence,
        now_epoch_us=now_epoch_us(),
        created_at=occurred_at,
    )
    store.transition_controlled_experiment(
        snapshot.projection,
        target_status=ExperimentStatus.COMPLETED,
        lease=lease,
        now_epoch_us=now_epoch_us(),
        occurred_at=occurred_at,
        attempt_started=False,
        reason_code="evidence_collection_completed",
    )
    reloaded = reload_snapshot(snapshot.projection.record.experiment_id)
    return reloaded, SchedulerTickState.COMPLETED


def cancel_failed_candidate_folds(
    *,
    store: ExperimentSchedulerStoreProtocol,
    snapshot: ExperimentSchedulerSnapshot,
    lease: SchedulerLease,
    now_epoch_us: Callable[[], int],
    occurred_at: datetime,
    vocabulary: SnapshotVocabulary,
) -> bool:
    """
    Cancel queued folds of failed candidates.

    Returns ``True`` iff at least one fold was cancelled, so the caller knows
    to reload the persisted snapshot before continuing the tick. Returns
    ``False`` when there are no failed candidates (no side effects).
    """
    failed_candidates = candidate_failure_ids(snapshot, vocabulary)
    if not failed_candidates:
        return False
    for fold in snapshot.folds:
        if (
            fold.spec.key.candidate_id in failed_candidates
            and fold.projection.status is ExperimentStatus.QUEUED
        ):
            store.transition_fold(
                fold,
                target_status=ExperimentStatus.CANCELLED,
                failure_code=None,
                lease=lease,
                now_epoch_us=now_epoch_us(),
                occurred_at=occurred_at,
            )
    return True
