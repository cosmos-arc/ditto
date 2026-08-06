"""Persisted progress and tick-result projection for the coordinator."""

from __future__ import annotations

from ditto_application.processes.experiments import (
    _coordinator_snapshot as snapshot_rules,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentDispatch,
    ExperimentProgress,
    SchedulerTickResult,
    SchedulerTickState,
)
from ditto_application.processes.experiments._coordinator_snapshot import (
    SnapshotVocabulary,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)


class CoordinatorResultBuilder:
    """Calculate observable progress from one validated durable snapshot."""

    def __init__(self, vocabulary: SnapshotVocabulary) -> None:
        self._vocabulary = vocabulary

    def progress(self, snapshot: ExperimentSchedulerSnapshot) -> ExperimentProgress:
        """Project worker capacity and terminal counts without inferred state."""
        vocabulary = self._vocabulary
        snapshot_rules.validate_durable_worker_capacity(snapshot, vocabulary)
        live_attempts = tuple(
            attempt
            for attempt in snapshot.attempts
            if attempt.projection.status in vocabulary.live_statuses
        )
        return ExperimentProgress(
            experiment_id=snapshot.projection.record.experiment_id,
            stage=snapshot.projection.record.stage,
            worker_limit=snapshot.launch_spec.worker_count,
            available_capacity=max(
                0,
                snapshot.launch_spec.worker_count - len(live_attempts),
            ),
            total_fold_count=len(snapshot.folds),
            terminal_fold_count=sum(
                1
                for fold in snapshot.folds
                if fold.projection.status in vocabulary.terminal_work_statuses
            ),
            live_attempt_count=len(live_attempts),
            completed_attempt_count=sum(
                1
                for attempt in snapshot.attempts
                if str(attempt.projection.status) == "completed"
            ),
            failed_candidate_attempt_count=sum(
                1
                for attempt in snapshot.attempts
                if attempt.projection.failure_code is vocabulary.candidate_failed_code
            ),
            hard_failure_count=snapshot_rules.hard_failure_count(
                snapshot,
                vocabulary,
            ),
        )

    def result(
        self,
        state: SchedulerTickState,
        snapshot: ExperimentSchedulerSnapshot,
        dispatches: tuple[ExperimentDispatch, ...],
    ) -> SchedulerTickResult:
        """Return a bounded tick result with persisted progress."""
        return SchedulerTickResult(
            state=state,
            experiment_id=snapshot.projection.record.experiment_id,
            dispatches=dispatches,
            progress=self.progress(snapshot),
        )

    @staticmethod
    def empty(state: SchedulerTickState) -> SchedulerTickResult:
        """Return a tick result with no selected experiment."""
        return SchedulerTickResult(state, None, (), None)
