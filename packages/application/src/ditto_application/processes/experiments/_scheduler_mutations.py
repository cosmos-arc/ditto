"""Durable scheduler mutations shared by experiment control paths."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptView,
    CandidateId,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentReaderProtocol,
    ExperimentStatus,
    ExperimentWriterProtocol,
    FoldView,
    SchedulerLease,
    StatusEventRecord,
)


class ExperimentMutationStoreMixin:
    """Implement mutation-specific scheduler storage operations."""

    _reader: ExperimentReaderProtocol
    _writer: ExperimentWriterProtocol

    def list_status_events(
        self, experiment_id: ExperimentId
    ) -> tuple[StatusEventRecord, ...]:
        return self._reader.list_status_events(experiment_id)

    def list_experiments(self) -> tuple[ExperimentProjection, ...]:
        return tuple(self._reader.list_experiments())

    def get_launch_spec(
        self,
        experiment_id: ExperimentId,
    ) -> ExperimentLaunchSpec | None:
        return self._reader.get_launch_spec(experiment_id)

    def list_experiment_artifacts(
        self,
        experiment_id: ExperimentId,
    ) -> tuple[ArtifactRecord, ...]:
        return self._reader.list_experiment_artifacts(experiment_id)

    def record_candidate_selection(
        self,
        experiment_id: ExperimentId,
        candidate_id: CandidateId,
        *,
        expected_revision: int,
        lease: SchedulerLease,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object],
    ) -> ExperimentProjection:
        """Append one preselection receipt through the existing event envelope."""
        return self._writer.record_candidate_selection(
            experiment_id,
            candidate_id,
            expected_revision=expected_revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            detail=detail,
        )

    def transition_operator_experiment(
        self,
        projection: ExperimentProjection,
        *,
        target_status: ExperimentStatus,
        target_desired_state: ExperimentDesiredState,
        expected_revision: int,
        occurred_at: datetime,
        reason_code: str,
        detail: Mapping[str, object] | None = None,
    ) -> ExperimentProjection:
        return self._writer.transition_experiment(
            projection.record.experiment_id,
            target_status=target_status,
            target_desired_state=target_desired_state,
            target_stage=projection.record.stage,
            failure_code=None,
            expected_revision=expected_revision,
            occurred_at=occurred_at,
            attempt_started=False,
            precondition_repairable=False,
            reason_code=reason_code,
            detail=dict(detail or {}),
        )

    def retry_terminal_fold(
        self,
        fold: FoldView,
        parent_attempt: AttemptView,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        occurred_at: datetime,
        detail: Mapping[str, object] | None = None,
    ) -> FoldView:
        projection = self._writer.requeue_failed_fold_for_retry(
            fold.spec.key,
            parent_attempt.spec.attempt_id,
            expected_fold_revision=fold.projection.revision,
            expected_parent_attempt_revision=parent_attempt.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=now_epoch_us,
            occurred_at=occurred_at,
            detail={
                "requested_by": lease.owner_token,
                **dict(detail or {}),
            },
        )
        return FoldView(fold.spec, projection)


__all__ = ["ExperimentMutationStoreMixin"]
