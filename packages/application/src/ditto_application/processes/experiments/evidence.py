"""
Assemble the immutable R3 review packet from typed evidence.

The assembler is a pure orchestration seam: it evaluates the two-layer gate
engine against typed evidence and freezes the result into an immutable
``ReviewPacket``. Callers (queries, the promotion process) are responsible for
collecting the underlying evidence and reproduction hashes; nothing here
performs storage or execution I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ditto_analysis.experiments import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ContentHash,
    EvidenceGateInput,
    HardGateEvidence,
    PromotionObjective,
    ResearchMetricId,
    ResearchMetricValue,
    ReviewPacket,
    ReviewPacketLineage,
    evaluate_evidence_gates,
    evaluate_hard_gates,
)

__all__ = ["ReviewPacketInput", "assemble_review_packet"]


@dataclass(frozen=True, slots=True)
class ReviewPacketInput:
    """Typed evidence gathered by callers and frozen into a review packet."""

    experiment_id: str
    candidate_id: str | None
    fold_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]
    spec_hash: ContentHash
    resolved_spec_hash: ContentHash
    parameter_hash: ContentHash
    snapshot_hash: ContentHash
    registry_hash: ContentHash
    objective: PromotionObjective
    objective_payload_hash: ContentHash
    hard_evidence: HardGateEvidence
    metric_values: Mapping[ResearchMetricId, ResearchMetricValue]
    comparison_payload_hash: ContentHash | None
    r1_impact_payload_hash: ContentHash | None
    selection_evidence_artifact_id: str | None
    holdout_claim_id: str | None
    candidate_rationale: str


def assemble_review_packet(packet_input: ReviewPacketInput) -> ReviewPacket:
    """Evaluate gates and freeze one immutable review packet."""
    hard_evaluations = evaluate_hard_gates(packet_input.hard_evidence)
    evidence_evaluations = evaluate_evidence_gates(
        EvidenceGateInput(
            objective=packet_input.objective,
            metric_values=packet_input.metric_values,
        )
    )
    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id=packet_input.experiment_id,
            candidate_id=packet_input.candidate_id,
            fold_ids=packet_input.fold_ids,
            attempt_ids=packet_input.attempt_ids,
        ),
        spec_hash=packet_input.spec_hash,
        resolved_spec_hash=packet_input.resolved_spec_hash,
        parameter_hash=packet_input.parameter_hash,
        snapshot_hash=packet_input.snapshot_hash,
        registry_hash=packet_input.registry_hash,
        objective_payload_hash=packet_input.objective_payload_hash,
        gate_evaluations=hard_evaluations + evidence_evaluations,
        comparison_payload_hash=packet_input.comparison_payload_hash,
        r1_impact_payload_hash=packet_input.r1_impact_payload_hash,
        selection_evidence_artifact_id=packet_input.selection_evidence_artifact_id,
        holdout_claim_id=packet_input.holdout_claim_id,
        candidate_rationale=packet_input.candidate_rationale,
    )
