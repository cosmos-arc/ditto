"""
Snapshot vocabulary for the durable experiment coordinator.

Extracted from :mod:`coordinator` to keep it under its size budget. The
vocabulary binds the persisted experiment/fold/attempt status enums into the
immutable :class:`SnapshotVocabulary` consumed by the coordinator, its result
builder and the snapshot integrity rules. Only the vocabulary and the
coordinator-facing status constants live here; the building-block failure-code
sets stay private to this module.
rules. Only the vocabulary and the coordinator-facing status constants live
here; the building-block failure-code sets stay private to this module.
"""

from __future__ import annotations

from ditto_analysis.experiments import (
    ExperimentFailureCode,
    ExperimentFailurePolicy,
    ExperimentStage,
    ExperimentStatus,
    FoldRole,
)

from ditto_application.processes.experiments._coordinator_snapshot import (
    SnapshotVocabulary,
    erase_mapping_keys,
)

__all__ = [
    "_FIRST_RUN_FAILURES",
    "_LIVE",
    "_NEXT_STAGE",
    "_REPLAYABLE_TERMINAL_ATTEMPT",
    "_SNAPSHOT_VOCABULARY",
    "_STAGE_ROLE",
    "_TERMINAL_EXPERIMENT",
    "_TERMINAL_WORK",
]

_LIVE = frozenset({ExperimentStatus.QUEUED, ExperimentStatus.RUNNING})
_TERMINAL_WORK = frozenset(
    {
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
    }
)
_TERMINAL_EXPERIMENT = _TERMINAL_WORK | {
    ExperimentStatus.COMPLETED_WITH_FAILURES,
}
_HARD_FAILURES = frozenset(
    {
        ExperimentFailureCode.INPUT_HASH_MISMATCH,
        ExperimentFailureCode.SYSTEM_ERROR,
    }
)
_FIRST_RUN_FAILURES = _HARD_FAILURES | {ExperimentFailureCode.CANDIDATE_FAILED}
_REPLAYABLE_TERMINAL_ATTEMPT = frozenset(
    {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED}
)
_STAGE_ROLE = {
    ExperimentStage.EXPLORATION: FoldRole.EXPLORATION,
    ExperimentStage.WALK_FORWARD: FoldRole.WALK_FORWARD,
    ExperimentStage.HOLDOUT: FoldRole.HOLDOUT,
}
_NEXT_STAGE = {
    ExperimentStage.EXPLORATION: ExperimentStage.WALK_FORWARD,
    ExperimentStage.WALK_FORWARD: ExperimentStage.CANDIDATE_SELECTION,
    ExperimentStage.HOLDOUT: ExperimentStage.EVIDENCE,
}
_SNAPSHOT_VOCABULARY = SnapshotVocabulary(
    live_statuses=_LIVE,
    terminal_work_statuses=_TERMINAL_WORK,
    hard_failure_codes=_HARD_FAILURES,
    first_run_failure_codes=_FIRST_RUN_FAILURES,
    replayable_terminal_statuses=_REPLAYABLE_TERMINAL_ATTEMPT,
    failed_status=ExperimentStatus.FAILED,
    queued_status=ExperimentStatus.QUEUED,
    running_status=ExperimentStatus.RUNNING,
    cancelled_status=ExperimentStatus.CANCELLED,
    candidate_failed_code=ExperimentFailureCode.CANDIDATE_FAILED,
    fail_fast_policy=ExperimentFailurePolicy.FAIL_FAST,
    stage_role=erase_mapping_keys(_STAGE_ROLE),
    role_order=erase_mapping_keys(
        {
            FoldRole.EXPLORATION: 0,
            FoldRole.WALK_FORWARD: 1,
            FoldRole.HOLDOUT: 2,
        },
    ),
    stage_role_ceiling=erase_mapping_keys(
        {
            ExperimentStage.EXPLORATION: 0,
            ExperimentStage.WALK_FORWARD: 1,
            ExperimentStage.CANDIDATE_SELECTION: 1,
            ExperimentStage.HOLDOUT: 2,
            ExperimentStage.EVIDENCE: 2,
        },
    ),
    prior_fold_roles=erase_mapping_keys(
        {
            ExperimentStage.PREFLIGHT: (),
            ExperimentStage.EXPLORATION: (),
            ExperimentStage.WALK_FORWARD: (FoldRole.EXPLORATION,),
            ExperimentStage.CANDIDATE_SELECTION: (
                FoldRole.EXPLORATION,
                FoldRole.WALK_FORWARD,
            ),
            ExperimentStage.HOLDOUT: (
                FoldRole.EXPLORATION,
                FoldRole.WALK_FORWARD,
            ),
            ExperimentStage.EVIDENCE: (
                FoldRole.EXPLORATION,
                FoldRole.WALK_FORWARD,
                FoldRole.HOLDOUT,
            ),
        },
    ),
)
