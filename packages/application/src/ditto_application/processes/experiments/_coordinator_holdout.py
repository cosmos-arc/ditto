"""Holdout-specific coordinator orchestration over application-local facades."""

from __future__ import annotations

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._coordinator_snapshot import (
    scheduler_error,
)
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
    HoldoutCandidateSelectionProvider,
    HoldoutClaimProcess,
    HoldoutClaimReceipt,
    HoldoutSelectionEvidenceProvider,
)
from ditto_application.processes.experiments.lease_authority import (
    LeaseAuthority,
    run_unfenced_scheduler_operation,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentId,
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStoreProtocol,
    ExperimentStage,
    ExperimentStatus,
    FirstAttemptFactory,
)


def _error(reason: str) -> None:
    raise scheduler_error("EXPERIMENT_INTEGRITY_FAILED", reason)


class HoldoutCoordinatorAuthority:
    """Bind operator holdout claims to the coordinator's live lease authority."""

    def __init__(
        self,
        *,
        store: ExperimentSchedulerStoreProtocol,
        first_attempt_factory: FirstAttemptFactory,
        selection_evidence_provider: HoldoutSelectionEvidenceProvider | None,
        authority: LeaseAuthority,
        candidate_selection_provider: HoldoutCandidateSelectionProvider | None = None,
    ) -> None:
        self._store = store
        self._process = HoldoutClaimProcess(
            store=store,
            first_attempt_factory=first_attempt_factory,
            selection_evidence_provider=selection_evidence_provider,
            candidate_selection_provider=candidate_selection_provider,
        )
        self._authority = authority

    def claim_candidate(
        self,
        request: ClaimHoldoutCandidateRequest,
    ) -> HoldoutClaimReceipt:
        """Replay without authority, otherwise commit under the current fence."""
        snapshot = run_unfenced_scheduler_operation(
            lambda: self._store.load_snapshot(ExperimentId(request.experiment_id))
        )
        if snapshot.holdout_claim is not None:
            return run_unfenced_scheduler_operation(
                lambda: self._process.claim_candidate(
                    request,
                    lease=None,
                    now_epoch_us=None,
                )
            )
        try:
            return run_unfenced_scheduler_operation(
                lambda: self._process.replay_candidate(request)
            )
        except AppProcessError as exc:
            if (
                exc.details.get("code") != "SPEC_INVALID"
                or exc.details.get("reason") != "holdout_lease_required"
            ):
                raise
        return self._authority.execute_operator(
            lambda lease, now_epoch_us: self._process.claim_candidate(
                request,
                lease=lease,
                now_epoch_us=now_epoch_us(),
            )
        )


def validate_holdout_snapshot(snapshot: ExperimentSchedulerSnapshot) -> None:
    """Bind every persisted holdout attempt to one complete immutable claim."""
    holdout_folds = tuple(
        fold for fold in snapshot.folds if str(fold.spec.fold_role) == "holdout"
    )
    holdout_attempts = tuple(
        attempt
        for attempt in snapshot.attempts
        if any(attempt.spec.fold_key == fold.spec.key for fold in holdout_folds)
    )
    claim = snapshot.holdout_claim
    if claim is None:
        if holdout_attempts and snapshot.projection.record.stage in {
            ExperimentStage.HOLDOUT,
            ExperimentStage.EVIDENCE,
        }:
            _error("holdout_attempt_without_claim")
        return
    if snapshot.projection.record.stage is ExperimentStage.CANDIDATE_SELECTION:
        _error("holdout_claim_stage_drift")
    selected = tuple(
        fold
        for fold in holdout_folds
        if str(fold.spec.key.candidate_id) == claim.candidate_id
        and str(fold.spec.key.fold_id) == claim.fold_id
    )
    candidates = tuple(
        candidate
        for candidate in snapshot.launch_spec.candidates
        if str(candidate.candidate_id) == claim.candidate_id
    )
    bindings = tuple(
        binding
        for binding in snapshot.launch_spec.execution_bindings
        if str(binding.candidate_id) == claim.candidate_id
    )
    if (
        claim.experiment_id != str(snapshot.projection.record.experiment_id)
        or len(selected) != 1
        or len(candidates) != 1
        or len(bindings) != 1
    ):
        _error("holdout_claim_lineage_drift")
    fold = selected[0]
    candidate = candidates[0]
    binding = bindings[0]
    if (
        str(candidate.parameter_hash) != claim.parameters_hash
        or str(binding.parameter_hash) != claim.parameters_hash
        or str(binding.resolved_spec_hash) != claim.resolved_spec_hash
        or str(snapshot.launch_spec.snapshot_id) != claim.snapshot_id
        or fold.spec.test_window.start.isoformat() != claim.window_start
        or fold.spec.test_window.end.isoformat() != claim.window_end
    ):
        _error("holdout_claim_binding_drift")
    if any(
        other is not fold and other.projection.status is not ExperimentStatus.CANCELLED
        for other in holdout_folds
    ):
        _error("holdout_unselected_fold_not_cancelled")
    if any(
        attempt.spec.fold_key != fold.spec.key
        or str(attempt.spec.reproduction_fingerprint) != claim.reproduction_fingerprint
        for attempt in holdout_attempts
    ):
        _error("holdout_claim_attempt_drift")


def selected_holdout_fold_ids(
    snapshot: ExperimentSchedulerSnapshot,
) -> frozenset[str] | None:
    """Return the single dispatchable holdout fold identity, if claimed."""
    claim = snapshot.holdout_claim
    if claim is None:
        return None
    return frozenset({claim.fold_id})
