"""
Collect and publish governed R3 review packets from persisted evidence.

The collector is the R3 evidence-stage seam: it loads one durable experiment
snapshot, reads the persisted ``preflight_passed`` event, assembles the typed
hard-gate view, evaluates the eleven hard-correctness gates, freezes the result
into an immutable :class:`ReviewPacket`, and publishes it through the durable
writer protocol.

This is the V1 closure (design section 6): the eleven hard gates are projected
from persisted facts; ``r2_live_gate`` is pinned to ``NOT_EVALUATED``; metric,
comparison, R1-impact, and selection-artifact evidence are intentionally
deferred to Task 3b and surface here as empty/``None`` placeholders that the
review-packet assembler accepts without violating the schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from ditto_analysis.experiments import (
    AttemptView,
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
    ReviewPacket,
    StatusEventRecord,
    collect_hard_gate_evidence,
    encode_launch_spec,
)
from ditto_analysis.experiments.trial_ledger import (
    promotion_objective_content_hash,
)

from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
)
from ditto_application.processes.experiments._holdout_contract import (
    PersistedHoldoutClaim,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.evidence import (
    ReviewPacketInput,
    assemble_review_packet,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStoreProtocol,
)

__all__ = ["ExperimentEvidenceCollector"]


#: V1 placeholder for the cost-config content hash. The ``cost_assumptions`` gate
#: is satisfied unconditionally by a present hash (design section 6); V2 will
#: replace this with a real cross-candidate consistency hash.
_PLACEHOLDER_COST_CONFIG_HASH = ContentHash("0" * 64)


@dataclass(frozen=True, slots=True)
class ExperimentEvidenceCollector:
    """Collect and publish R3 review packets from persisted experiment evidence."""

    scheduler_store: ExperimentSchedulerStoreProtocol
    reader: ExperimentReaderProtocol
    writer: ExperimentWriterProtocol

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
        events = self.reader.list_status_events(experiment_id)
        detail = _read_preflight_detail(events, experiment_id)
        hard_view = _build_hard_gate_view(snapshot, detail, claim)
        hard_evidence = collect_hard_gate_evidence(hard_view)
        rationale = _candidate_rationale(snapshot.launch_spec, claim.candidate_id)
        packet_input = _build_packet_input(
            snapshot,
            detail,
            claim,
            hard_evidence,
            rationale,
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
    for event in events:
        if (
            event.experiment_id == experiment_id
            and event.reason_code == "preflight_passed"
        ):
            return event.detail
    raise experiment_process_error("preflight_passed_event_not_found")


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


def _walk_forward_folds(
    folds: tuple[FoldView, ...],
    candidate_id: CandidateId,
) -> tuple[FoldView, ...]:
    """Filter walk-forward folds for one candidate, preserving persistence order."""
    return tuple(
        fold
        for fold in folds
        if _is_walk_forward(fold) and fold.spec.key.candidate_id == candidate_id
    )


def _months_in_window(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> int:
    """
    Inclusive calendar-month span between two year/month pairs.

    Both endpoints count as full months: ``(2016, 1)`` to ``(2016, 1)`` returns
    ``1`` and ``(2016, 1)`` to ``(2017, 1)`` returns ``13``. The inclusivity
    mirrors the R3 walk-forward test-window semantics, where the start and end
    months of ``FoldPersistenceSpec.test_window`` both contribute to the OOS
    span that the ``ninety_six_month`` gate sums across folds.
    """
    return (end_year - start_year) * 12 + (end_month - start_month) + 1


def _oos_month_count(walk_forward_folds: tuple[FoldView, ...]) -> int:
    """Aggregate inclusive test-window months across walk-forward folds."""
    return sum(
        _months_in_window(
            fold.spec.test_window.start.year,
            fold.spec.test_window.start.month,
            fold.spec.test_window.end.year,
            fold.spec.test_window.end.month,
        )
        for fold in walk_forward_folds
    )


def _purge_embargo_configured(walk_forward_folds: tuple[FoldView, ...]) -> bool:
    """True when any walk-forward fold declares purge or embargo sessions."""
    return any(
        fold.spec.purge_sessions > 0 or fold.spec.embargo_sessions > 0
        for fold in walk_forward_folds
    )


def _reproduction_fingerprints(
    folds: tuple[FoldView, ...],
    attempts: tuple[AttemptView, ...],
) -> tuple[ContentHash, ...]:
    """
    Collect non-empty reproduction fingerprints for one candidate's attempts.

    Design section 9 makes artifact/metric absence a non-blocking packet outcome:
    an empty tuple lets the ``reproduction`` gate objectively evaluate to
    ``GateOutcome.FAIL`` instead of failing the whole tick.
    """
    fold_keys = frozenset(fold.spec.key for fold in folds)
    return tuple(
        attempt.spec.reproduction_fingerprint
        for attempt in attempts
        if attempt.spec.fold_key in fold_keys
    )


def _artifact_complete(
    walk_forward_folds: tuple[FoldView, ...],
    attempts: tuple[AttemptView, ...],
) -> bool:
    """Proxy artifact completeness via walk-forward attempt status (V1 closure)."""
    fold_keys = frozenset(fold.spec.key for fold in walk_forward_folds)
    completed_keys = frozenset(
        attempt.spec.fold_key
        for attempt in attempts
        if attempt.projection.status is ExperimentStatus.COMPLETED
    )
    return bool(fold_keys) and fold_keys.issubset(completed_keys)


def _build_hard_gate_view(
    snapshot: ExperimentSchedulerSnapshot,
    detail: Mapping[str, object],
    claim: PersistedHoldoutClaim,
) -> HardGateEvidenceView:
    """Assemble the thirteen hard-gate view fields from persisted evidence."""
    launch_spec = snapshot.launch_spec
    selected_id = CandidateId(claim.candidate_id)
    selected_walk_forward = _walk_forward_folds(snapshot.folds, selected_id)
    all_walk_forward = tuple(fold for fold in snapshot.folds if _is_walk_forward(fold))
    fingerprints = _reproduction_fingerprints(selected_walk_forward, snapshot.attempts)
    manifest = project_snapshot_manifest(detail)
    # fold_protocol is per-launch (shared across candidates), so ``all_walk_forward``
    # is equivalent to ``selected_walk_forward`` for the purge/embargo check in V1;
    # passing ``all_walk_forward`` aligns with ``_artifact_complete`` and design
    # section 6 ("所有 fold") so the gate stays objective if a future launch splits
    # purge/embargo configuration per candidate.
    return HardGateEvidenceView(
        certified_snapshot=_certified_snapshot(detail),
        snapshot_id=str(launch_spec.snapshot_id),
        oos_month_count=_oos_month_count(selected_walk_forward),
        pit_policy=manifest.pit_policy,
        purge_embargo_configured=_purge_embargo_configured(all_walk_forward),
        reproduction_fingerprints=fingerprints,
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
        artifact_complete=_artifact_complete(all_walk_forward, snapshot.attempts),
        artifact_missing=(),
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


def _attempt_ids(
    folds: tuple[FoldView, ...],
    attempts: tuple[AttemptView, ...],
) -> tuple[str, ...]:
    """
    Preserve persisted attempt order for one candidate's walk-forward folds.

    Design section 8.4 requires "每个 fold 取其终态 attempt": only attempts whose
    projection has reached ``ExperimentStatus.COMPLETED`` are bound to the
    review packet, so in-progress or retry attempts never inflate the lineage.
    """
    fold_keys = frozenset(fold.spec.key for fold in folds)
    return tuple(
        str(attempt.spec.attempt_id)
        for attempt in attempts
        if attempt.spec.fold_key in fold_keys
        and attempt.projection.status is ExperimentStatus.COMPLETED
    )


def _build_packet_input(
    snapshot: ExperimentSchedulerSnapshot,
    detail: Mapping[str, object],
    claim: PersistedHoldoutClaim,
    hard_evidence: HardGateEvidence,
    rationale: str,
) -> ReviewPacketInput:
    """Assemble the eighteen-field review-packet input (V1 placeholders inline)."""
    launch_spec = snapshot.launch_spec
    selected_id = CandidateId(claim.candidate_id)
    walk_forward_folds = _walk_forward_folds(snapshot.folds, selected_id)
    candidate = _selected_candidate(launch_spec, selected_id)
    binding = _selected_binding(launch_spec, selected_id)
    manifest = project_snapshot_manifest(detail)
    return ReviewPacketInput(
        experiment_id=str(snapshot.projection.record.experiment_id),
        candidate_id=claim.candidate_id,
        fold_ids=tuple(str(fold.spec.key.fold_id) for fold in walk_forward_folds),
        attempt_ids=_attempt_ids(walk_forward_folds, snapshot.attempts),
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
        # V1 placeholders (design §9/§13): empty metric_values lets the
        # evidence gates evaluate to NOT_EVALUATED; the payload hashes and
        # selection-evidence artifact id are Task 3b closures (r1_impact is
        # user-confirmed deferred). All four are accepted by the assembler
        # without violating the ReviewPacketInput schema.
        metric_values={},
        comparison_payload_hash=None,
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
