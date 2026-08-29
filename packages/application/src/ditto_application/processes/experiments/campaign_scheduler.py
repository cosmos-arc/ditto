"""Campaign scheduling adapter over the existing durable R3 scheduler lease."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStatus,
    LeaseFence,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.autonomous_campaign import (
    CampaignScheduledTrial,
    CampaignTrialRetryRequest,
    CampaignTrialScheduleRequest,
    CampaignTrialSchedulerPort,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)

__all__ = ["ExistingExperimentCampaignScheduler"]

_CAMPAIGN_LEASE_DURATION_US = 60_000_000
_OWNER_IDENTITY = "r5-autonomous-campaign"
_TERMINAL_EXPERIMENT_STATUSES = frozenset(
    {
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.COMPLETED_WITH_FAILURES,
        ExperimentStatus.FAILED,
    }
)


def _error(message: str, *, code: str, reason: str) -> AppProcessError:
    return AppProcessError(message, details={"code": code, "reason": reason})


class ExistingExperimentCampaignScheduler(CampaignTrialSchedulerPort):
    """Reserve Campaign work through the existing scheduler slot and fold matrix."""

    def __init__(
        self,
        *,
        store: ExperimentSchedulerStoreProtocol,
        owner_token: str = _OWNER_IDENTITY,
        lease_duration_us: int = _CAMPAIGN_LEASE_DURATION_US,
    ) -> None:
        if not owner_token or owner_token != owner_token.strip():
            raise _error(
                "owner_token must be a non-empty canonical string",
                code="CAMPAIGN_SCHEDULER_INVALID",
                reason="campaign_scheduler_configuration_invalid",
            )
        if type(lease_duration_us) is not int or lease_duration_us <= 0:
            raise _error(
                "lease_duration_us must be positive",
                code="CAMPAIGN_SCHEDULER_INVALID",
                reason="campaign_scheduler_configuration_invalid",
            )
        self._store = store
        self._owner_token = owner_token
        self._lease_duration_us = lease_duration_us

    def required_fold_run_count(self, campaign_id: ExperimentId) -> int:
        """Read the immutable fold matrix before the Campaign reserves budget."""
        return self._fold_run_count(campaign_id)

    def schedule_trial(
        self,
        request: CampaignTrialScheduleRequest,
        *,
        now_epoch_us: int,
    ) -> CampaignScheduledTrial:
        """Fence one trial and reserve its frozen per-candidate fold count."""
        lease = self._claim_or_reuse(request.campaign_id, now_epoch_us)
        fold_run_count = self._fold_run_count(request.campaign_id)
        if fold_run_count > request.fold_run_budget_remaining:
            raise _error(
                "frozen fold matrix exceeds remaining Campaign authority",
                code="CAMPAIGN_BUDGET_EXHAUSTED",
                reason="campaign_fold_budget_exhausted",
            )
        return CampaignScheduledTrial(
            lease=lease,
            fold_run_count=fold_run_count,
        )

    def schedule_retry(
        self,
        request: CampaignTrialRetryRequest,
        *,
        now_epoch_us: int,
    ) -> LeaseFence:
        """Fence a retry without creating another statistical trial."""
        return self._claim_or_reuse(request.campaign_id, now_epoch_us)

    def cancel_campaign(
        self,
        campaign_id: ExperimentId,
        *,
        now_epoch_us: int,
    ) -> None:
        """Persist the existing scheduler's idempotent operator cancel intent."""
        snapshot = self._store.load_snapshot(campaign_id)
        projection = snapshot.projection
        status = projection.record.status
        if (
            status in _TERMINAL_EXPERIMENT_STATUSES
            or status is ExperimentStatus.CANCEL_REQUESTED
        ):
            return
        self._store.transition_operator_experiment(
            projection,
            target_status=ExperimentStatus.CANCEL_REQUESTED,
            target_desired_state=ExperimentDesiredState.CANCEL,
            expected_revision=projection.revision,
            occurred_at=_datetime_from_epoch_us(now_epoch_us),
            reason_code="autonomous_campaign_cancel",
            detail={"campaign_id": str(campaign_id)},
        )

    def _claim_or_reuse(
        self,
        campaign_id: ExperimentId,
        now_epoch_us: int,
    ) -> LeaseFence:
        if type(now_epoch_us) is not int or now_epoch_us < 0:
            raise _error(
                "now_epoch_us must be non-negative",
                code="CAMPAIGN_SCHEDULER_INVALID",
                reason="campaign_scheduler_time_invalid",
            )
        self._store.load_snapshot(campaign_id)
        slot = self._store.get_scheduler_slot()
        if (
            slot.experiment_id == campaign_id
            and slot.owner_token == self._owner_token
            and slot.lease_until_epoch_us is not None
            and slot.lease_until_epoch_us > now_epoch_us
        ):
            return LeaseFence(
                experiment_id=campaign_id,
                owner_token=self._owner_token,
                revision=slot.revision,
                lease_until_epoch_us=slot.lease_until_epoch_us,
            )
        if (
            slot.owner_token is not None
            and slot.lease_until_epoch_us is not None
            and slot.lease_until_epoch_us > now_epoch_us
        ):
            raise _error(
                "the experiment scheduler lease is owned elsewhere",
                code="LEASE_LOST",
                reason="campaign_lease_lost",
            )
        try:
            lease = self._store.try_claim_lease(
                campaign_id,
                self._owner_token,
                expected_revision=slot.revision,
                now_epoch_us=now_epoch_us,
                lease_until_epoch_us=now_epoch_us + self._lease_duration_us,
            )
        except AnalysisError as exc:
            raise _error(
                "the Campaign could not acquire the experiment scheduler lease",
                code="LEASE_LOST",
                reason="campaign_lease_lost",
            ) from exc
        if lease is None:
            raise _error(
                "the Campaign lost the experiment scheduler lease race",
                code="LEASE_LOST",
                reason="campaign_lease_lost",
            )
        return lease.fence

    def _fold_run_count(self, campaign_id: ExperimentId) -> int:
        snapshot = self._store.load_snapshot(campaign_id)
        counts = Counter(fold.spec.key.candidate_id for fold in snapshot.folds)
        unique_counts = frozenset(counts.values())
        if not counts or len(unique_counts) != 1:
            raise _error(
                "the frozen experiment fold matrix is incomplete or asymmetric",
                code="CAMPAIGN_SCHEDULER_INVALID",
                reason="campaign_fold_matrix_invalid",
            )
        return next(iter(unique_counts))


def _datetime_from_epoch_us(value: int) -> datetime:
    """Convert an epoch-us scheduler timestamp without float rounding."""
    seconds, microseconds = divmod(value, 1_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(
        microseconds=microseconds
    )
