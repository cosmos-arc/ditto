"""
Collect and publish governed R3 review packets from persisted evidence.

The collector is the R3 evidence-stage seam: it loads one durable experiment
snapshot, reads the persisted ``preflight_passed`` event, assembles the typed
hard-gate view, evaluates the eleven hard-correctness gates, freezes the result
into an immutable :class:`ReviewPacket`, and publishes it through the durable
writer protocol.

The selected candidate's metrics and comparison hash come from exact persisted
walk-forward attempts and verified report artifacts. Missing reports remain an
honest packet outcome; malformed reports fail closed before publication.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from ditto_analysis.experiments import (
    R3_COMPARISON_METRIC_IDS,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ContentHash,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentReaderProtocol,
    ExperimentStatus,
    ExperimentWriterProtocol,
    FoldRole,
    FoldView,
    HardGateEvidence,
    HardGateEvidenceView,
    LeaseFence,
    ResearchMetricId,
    ResearchMetricValue,
    ReviewPacket,
    StatusEventRecord,
    collect_hard_gate_evidence,
    encode_launch_spec,
)
from ditto_analysis.experiments.trial_ledger import (
    promotion_objective_content_hash,
)

from ditto_application.processes.experiments._evidence_inputs import (
    SnapshotManifestProjection,
    project_snapshot_manifest,
)
from ditto_application.processes.experiments._holdout_contract import (
    PersistedHoldoutClaim,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    CollectedWalkForwardEvidence,
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.comparison import (
    CandidateFoldEvidence,
    FoldOutcome,
)
from ditto_application.processes.experiments.evidence import (
    ReviewPacketInput,
    assemble_review_packet,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPreflightReport,
    reconstruct_preflight_report,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStoreProtocol,
)
from ditto_application.processes.experiments.walk_forward import WalkForwardCandidate

__all__ = ["ExperimentEvidenceCollector"]


#: V1 placeholder for the cost-config content hash. The ``cost_assumptions`` gate
#: is satisfied unconditionally by a present hash (design section 6); V2 will
#: replace this with a real cross-candidate consistency hash.
_PLACEHOLDER_COST_CONFIG_HASH = ContentHash("0" * 64)
_REQUIRED_SELECTED_WALK_FORWARD_FOLDS = 2


@dataclass(frozen=True, slots=True)
class ExperimentEvidenceCollector:
    """Collect and publish R3 review packets from persisted experiment evidence."""

    scheduler_store: ExperimentSchedulerStoreProtocol
    reader: ExperimentReaderProtocol
    writer: ExperimentWriterProtocol
    walk_forward_assembler: WalkForwardEvidenceAssembler

    def collect(
        self,
        experiment_id: ExperimentId,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        created_at: datetime,
    ) -> ReviewPacket:
        """Load evidence, evaluate hard gates, and publish one review packet."""
        snapshot = self.scheduler_store.load_snapshot(experiment_id)
        claim = snapshot.holdout_claim
        if claim is None:
            raise experiment_process_error("evidence_requires_holdout_claim")
        selected_id = _validate_holdout_claim_lineage(snapshot, claim)
        events = self.reader.list_status_events(experiment_id)
        detail = _read_preflight_detail(events, experiment_id)
        preflight = reconstruct_preflight_report(detail)
        manifest = project_snapshot_manifest(detail)
        collected = self.walk_forward_assembler.assemble(snapshot, manifest)
        selected, selected_rows = _selected_walk_forward_evidence(
            collected,
            selected_id,
        )
        hard_view = _build_hard_gate_view(
            snapshot,
            detail,
            manifest,
            preflight,
            claim,
            collected,
            selected_rows,
        )
        hard_evidence = collect_hard_gate_evidence(hard_view)
        rationale = _candidate_rationale(snapshot.launch_spec, claim.candidate_id)
        packet_input = _build_packet_input(
            snapshot,
            manifest,
            claim,
            hard_evidence,
            rationale,
            selected,
            selected_rows,
        )
        packet = assemble_review_packet(packet_input)
        self.writer.publish_review_packet(
            packet,
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
            created_at=created_at,
        )
        return packet


def _read_preflight_detail(
    events: tuple[StatusEventRecord, ...],
    experiment_id: ExperimentId,
) -> Mapping[str, object]:
    """
    Return the persisted detail of the unique ``preflight_passed`` event.

    The hardcoded ``preflight.identities.certification.ready`` path traced below
    mirrors the writer side: keep in sync with ``_launch_material.py`` (builds
    the detail payload), ``_preflight_shape.py`` (validates the payload shape),
    and ``_preflight_semantics.py`` (semantic checks on the parsed shape)
    whenever the preflight detail payload shape evolves.
    """
    matches = tuple(
        event.detail
        for event in events
        if (
            event.experiment_id == experiment_id
            and event.reason_code == "preflight_passed"
        )
    )
    if not matches:
        raise experiment_process_error("preflight_passed_event_not_found")
    if len(matches) != 1:
        raise experiment_process_error("preflight_passed_event_not_unique")
    return matches[0]


def _mapping_field(
    mapping: Mapping[str, object],
    key: str,
    *,
    context: str,
) -> Mapping[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise experiment_process_error(context)
    return cast("Mapping[str, object]", value)


def _certified_snapshot(detail: Mapping[str, object]) -> bool:
    """Read the certification ready flag from the persisted preflight detail."""
    preflight = _mapping_field(detail, "preflight", context="preflight_missing")
    identities = _mapping_field(
        preflight, "identities", context="preflight_identities_missing"
    )
    certification = _mapping_field(
        identities, "certification", context="preflight_certification_missing"
    )
    ready = certification.get("ready")
    if type(ready) is not bool:
        raise experiment_process_error("preflight_certification_ready_missing")
    return ready


def _is_walk_forward(fold: FoldView) -> bool:
    return fold.spec.fold_role is FoldRole.WALK_FORWARD


def _purge_embargo_configured(walk_forward_folds: tuple[FoldView, ...]) -> bool:
    """True only when every walk-forward fold declares purge or embargo."""
    return bool(walk_forward_folds) and all(
        fold.spec.purge_sessions > 0 or fold.spec.embargo_sessions > 0
        for fold in walk_forward_folds
    )


def _artifact_complete(
    walk_forward_folds: tuple[FoldView, ...],
    missing_artifact_refs: tuple[str, ...],
) -> bool:
    """Require every family fold completed and every expected report present."""
    return (
        bool(walk_forward_folds)
        and all(
            fold.projection.status is ExperimentStatus.COMPLETED
            for fold in walk_forward_folds
        )
        and not missing_artifact_refs
    )


def _build_hard_gate_view(
    snapshot: ExperimentSchedulerSnapshot,
    detail: Mapping[str, object],
    manifest: SnapshotManifestProjection,
    preflight: ExperimentPreflightReport,
    claim: PersistedHoldoutClaim,
    collected: CollectedWalkForwardEvidence,
    selected_rows: tuple[CandidateFoldEvidence, ...],
) -> HardGateEvidenceView:
    """Assemble the thirteen hard-gate view fields from persisted evidence."""
    launch_spec = snapshot.launch_spec
    all_walk_forward = tuple(fold for fold in snapshot.folds if _is_walk_forward(fold))
    return HardGateEvidenceView(
        certified_snapshot=_certified_snapshot(detail),
        snapshot_id=str(launch_spec.snapshot_id),
        eligible_month_count=preflight.eligible_month_count,
        pit_policy=manifest.pit_policy,
        purge_embargo_configured=_purge_embargo_configured(all_walk_forward),
        reproduction_fingerprints=tuple(
            row.reproduction_fingerprint for row in selected_rows
        ),
        cost_config_hash=_PLACEHOLDER_COST_CONFIG_HASH,
        baseline_candidate_id=str(
            launch_spec.promotion_objective.baseline_candidate_id
        ),
        # Objective per design section 6: ``expected_trial_count`` is the
        # pre-registered current-trial declaration
        # (``trial_family.current_members``) and ``trial_count`` is the actually
        # expanded candidate count; mismatches fail the ``trial_declaration``
        # gate objectively.
        trial_count=len(launch_spec.candidates),
        expected_trial_count=len(
            launch_spec.promotion_objective.trial_family.current_members
        ),
        holdout_claim_id=claim.claim_id,
        artifact_complete=_artifact_complete(
            all_walk_forward,
            collected.missing_artifact_refs,
        ),
        artifact_missing=collected.missing_artifact_refs,
    )


def _selected_candidate(
    launch_spec: ExperimentLaunchSpec,
    candidate_id: CandidateId,
) -> CandidateSpec:
    for candidate in launch_spec.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise experiment_process_error("evidence_selected_candidate_missing")


def _selected_binding(
    launch_spec: ExperimentLaunchSpec,
    candidate_id: CandidateId,
) -> CandidateExecutionBinding:
    for binding in launch_spec.execution_bindings:
        if binding.candidate_id == candidate_id:
            return binding
    raise experiment_process_error("evidence_selected_binding_missing")


def _validate_holdout_claim_lineage(
    snapshot: ExperimentSchedulerSnapshot,
    claim: PersistedHoldoutClaim,
) -> CandidateId:
    """Fail closed unless the claim binds the exact launch and unique holdout."""
    launch = snapshot.launch_spec
    try:
        selected_id = CandidateId(claim.candidate_id)
    except (TypeError, ValueError):
        raise experiment_process_error("holdout_claim_evidence_lineage_drift") from None
    candidates = tuple(
        candidate
        for candidate in launch.candidates
        if candidate.candidate_id == selected_id
    )
    bindings = tuple(
        binding
        for binding in launch.execution_bindings
        if binding.candidate_id == selected_id
    )
    holdout_folds = tuple(
        fold
        for fold in snapshot.folds
        if fold.spec.fold_role is FoldRole.HOLDOUT
        and fold.spec.key.experiment_id == launch.experiment_id
        and fold.spec.key.candidate_id == selected_id
    )
    if (
        len(candidates) != 1
        or len(bindings) != 1
        or claim.experiment_id != str(launch.experiment_id)
        or claim.parameters_hash != str(candidates[0].parameter_hash)
        or claim.resolved_spec_hash != str(bindings[0].resolved_spec_hash)
        or claim.snapshot_id != str(launch.snapshot_id)
        or len(holdout_folds) != 1
        or claim.fold_id != str(holdout_folds[0].spec.key.fold_id)
        or claim.window_start != holdout_folds[0].spec.test_window.start.isoformat()
        or claim.window_end != holdout_folds[0].spec.test_window.end.isoformat()
    ):
        raise experiment_process_error("holdout_claim_evidence_lineage_drift")
    return selected_id


def _selected_walk_forward_evidence(
    collected: CollectedWalkForwardEvidence,
    selected_id: CandidateId,
) -> tuple[WalkForwardCandidate, tuple[CandidateFoldEvidence, ...]]:
    """Bind the holdout claim to one exact two-fold completed source pair."""
    candidates = tuple(
        candidate
        for candidate in collected.aggregation.candidates
        if candidate.candidate_id == selected_id
    )
    rows = tuple(
        row for row in collected.source_rows if row.candidate_id == selected_id
    )
    if len(candidates) != 1 or type(candidates[0]) is not WalkForwardCandidate:
        raise experiment_process_error("selected_walk_forward_candidate_not_unique")
    candidate = candidates[0]
    if (
        len(rows) != _REQUIRED_SELECTED_WALK_FORWARD_FOLDS
        or len(candidate.folds) != _REQUIRED_SELECTED_WALK_FORWARD_FOLDS
        or tuple(item.source for item in candidate.folds) != rows
        or any(row.outcome is not FoldOutcome.COMPLETED for row in rows)
        or len({row.fold_id for row in rows}) != _REQUIRED_SELECTED_WALK_FORWARD_FOLDS
        or len({row.attempt_id for row in rows})
        != _REQUIRED_SELECTED_WALK_FORWARD_FOLDS
    ):
        raise experiment_process_error("selected_walk_forward_incomplete")
    return candidate, rows


def _metric_values(
    selected: WalkForwardCandidate,
) -> dict[ResearchMetricId, ResearchMetricValue]:
    """Project evaluated values in fixed R3 comparison-schema order."""
    result: dict[ResearchMetricId, ResearchMetricValue] = {}
    for metric_id in R3_COMPARISON_METRIC_IDS:
        value = selected.metrics[metric_id].metric_value
        if value is not None:
            if type(value) is not ResearchMetricValue:
                raise experiment_process_error("invalid_walk_forward_metric_value")
            result[metric_id] = value
    return result


def _build_packet_input(
    snapshot: ExperimentSchedulerSnapshot,
    manifest: SnapshotManifestProjection,
    claim: PersistedHoldoutClaim,
    hard_evidence: HardGateEvidence,
    rationale: str,
    selected: WalkForwardCandidate,
    selected_rows: tuple[CandidateFoldEvidence, ...],
) -> ReviewPacketInput:
    """Assemble the review packet from exact selected walk-forward evidence."""
    launch_spec = snapshot.launch_spec
    selected_id = CandidateId(claim.candidate_id)
    candidate = _selected_candidate(launch_spec, selected_id)
    binding = _selected_binding(launch_spec, selected_id)
    return ReviewPacketInput(
        experiment_id=str(snapshot.projection.record.experiment_id),
        candidate_id=claim.candidate_id,
        fold_ids=tuple(str(row.fold_id) for row in selected_rows),
        attempt_ids=tuple(str(row.attempt_id) for row in selected_rows),
        spec_hash=encode_launch_spec(launch_spec).content_hash,
        resolved_spec_hash=binding.resolved_spec_hash,
        parameter_hash=candidate.parameter_hash,
        snapshot_hash=manifest.snapshot_hash,
        registry_hash=manifest.registry_hash,
        objective=launch_spec.promotion_objective,
        objective_payload_hash=promotion_objective_content_hash(
            launch_spec.promotion_objective
        ),
        hard_evidence=hard_evidence,
        metric_values=_metric_values(selected),
        comparison_payload_hash=selected.content_hash,
        # Explicit later-stage fields: neither is inferred from comparison
        # evidence. The selection-ledger publisher will supply its artifact id.
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id=None,
        holdout_claim_id=claim.claim_id,
        candidate_rationale=rationale,
    )


def _candidate_rationale(
    launch_spec: ExperimentLaunchSpec,
    selected_candidate_id: str,
) -> str:
    """Format the selected candidate's parameter delta vs the declared baseline."""
    selected_id = CandidateId(selected_candidate_id)
    selected = _selected_candidate(launch_spec, selected_id)
    baseline_id = launch_spec.promotion_objective.baseline_candidate_id
    baseline = _selected_candidate(launch_spec, baseline_id)
    selected_keys = set(selected.parameters)
    baseline_keys = set(baseline.parameters)
    added = sorted(selected_keys - baseline_keys)
    removed = sorted(baseline_keys - selected_keys)
    changed = sorted(
        key
        for key in (selected_keys & baseline_keys)
        if selected.parameters[key] != baseline.parameters[key]
    )
    return (
        f"selected={selected_candidate_id}; baseline={baseline_id}; "
        f"added={added}; removed={removed}; changed={changed}"
    )
