"""
Application review-packet read models extracted from the experiment facade.

Extracted from :mod:`queries.experiments` to keep it under its size budget.
These frozen dataclasses and the builder derive an application-owned view of
an immutable promotion review packet from the analysis-owned
:class:`~ditto_analysis.experiments.ReviewPacket`. The query facade re-exports
them so existing consumers keep their import paths unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_analysis.experiments import (
    ContentHash,
    ReviewPacket,
    review_blocked_by_hard_gates,
)

__all__ = [
    "ExperimentReviewPacketReadModel",
    "ReviewExposureWeightReadModel",
    "ReviewGateOutcome",
    "ReviewSelectionExposureReadModel",
    "ReviewSelectionTraceRef",
    "build_review_packet_read_model",
]


@dataclass(frozen=True, slots=True)
class ReviewGateOutcome:
    """One gate rule's identity and outcome in a review packet read model."""

    rule_id: str
    layer: str
    outcome: str


@dataclass(frozen=True, slots=True)
class ReviewSelectionTraceRef:
    """One verified positive selection-trace artifact reference in a packet."""

    artifact_kind: str
    artifact_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ReviewExposureWeightReadModel:
    """One plain exposure dimension weight for application consumers."""

    key: str
    weight: float


@dataclass(frozen=True, slots=True)
class ReviewSelectionExposureReadModel:
    """Plain v3 selection exposure summary; absent for persisted v1/v2 packets."""

    applicability: str
    lane: str
    industry_weights: tuple[ReviewExposureWeightReadModel, ...]
    size_bucket_weights: tuple[ReviewExposureWeightReadModel, ...]
    artifact_refs: tuple[ReviewSelectionTraceRef, ...]


@dataclass(frozen=True, slots=True)
class ExperimentReviewPacketReadModel:
    """Application view of one immutable promotion review packet."""

    experiment_id: str
    candidate_id: str | None
    bundle_hash: str
    hard_review_blocked: bool
    gate_outcomes: tuple[ReviewGateOutcome, ...]
    schema_version: int
    fold_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]
    spec_hash: str
    resolved_spec_hash: str
    parameter_hash: str
    snapshot_hash: str
    registry_hash: str
    objective_payload_hash: str
    comparison_payload_hash: str | None
    r1_impact_payload_hash: str | None
    selection_evidence_artifact_id: str | None
    holdout_claim_id: str | None
    candidate_rationale: str
    selection_trace_artifact_refs: tuple[ReviewSelectionTraceRef, ...]
    selection_exposure: ReviewSelectionExposureReadModel | None


def build_review_packet_read_model(
    packet: ReviewPacket,
) -> ExperimentReviewPacketReadModel:
    """Derive an application read model from an immutable review packet."""
    return ExperimentReviewPacketReadModel(
        experiment_id=packet.lineage.experiment_id,
        candidate_id=packet.lineage.candidate_id,
        bundle_hash=str(packet.bundle_hash),
        hard_review_blocked=review_blocked_by_hard_gates(packet.gate_evaluations),
        gate_outcomes=tuple(
            ReviewGateOutcome(
                rule_id=evaluation.rule_id,
                layer=evaluation.layer.value,
                outcome=evaluation.outcome.value,
            )
            for evaluation in packet.gate_evaluations
        ),
        schema_version=packet.schema_version,
        fold_ids=packet.lineage.fold_ids,
        attempt_ids=packet.lineage.attempt_ids,
        spec_hash=str(packet.spec_hash),
        resolved_spec_hash=str(packet.resolved_spec_hash),
        parameter_hash=str(packet.parameter_hash),
        snapshot_hash=str(packet.snapshot_hash),
        registry_hash=str(packet.registry_hash),
        objective_payload_hash=str(packet.objective_payload_hash),
        comparison_payload_hash=_optional_hash(packet.comparison_payload_hash),
        r1_impact_payload_hash=_optional_hash(packet.r1_impact_payload_hash),
        selection_evidence_artifact_id=packet.selection_evidence_artifact_id,
        holdout_claim_id=packet.holdout_claim_id,
        candidate_rationale=packet.candidate_rationale,
        selection_trace_artifact_refs=tuple(
            ReviewSelectionTraceRef(
                artifact_kind=ref.artifact_kind,
                artifact_id=ref.artifact_id,
                content_hash=str(ref.content_hash),
            )
            for ref in packet.selection_trace_artifact_refs
        ),
        selection_exposure=(
            None
            if packet.selection_exposure is None
            else ReviewSelectionExposureReadModel(
                applicability=packet.selection_exposure.applicability,
                lane=packet.selection_exposure.lane,
                industry_weights=tuple(
                    ReviewExposureWeightReadModel(item.key, item.weight)
                    for item in packet.selection_exposure.industry_weights
                ),
                size_bucket_weights=tuple(
                    ReviewExposureWeightReadModel(item.key, item.weight)
                    for item in packet.selection_exposure.size_bucket_weights
                ),
                artifact_refs=tuple(
                    ReviewSelectionTraceRef(
                        artifact_kind=ref.artifact_kind,
                        artifact_id=ref.artifact_id,
                        content_hash=str(ref.content_hash),
                    )
                    for ref in packet.selection_exposure.artifact_refs
                ),
            )
        ),
    )


def _optional_hash(value: ContentHash | None) -> str | None:
    """Render one optional content hash as a string, preserving ``None``."""
    return None if value is None else str(value)
