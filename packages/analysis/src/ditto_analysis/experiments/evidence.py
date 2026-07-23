"""
Immutable review evidence bundle for governed R3 promotion.

A review packet freezes the complete lineage, reproduction hashes, gate
results, comparison/R1 impact hashes, holdout and selection evidence, plus the
candidate rationale. Once assembled the payload is read-only and the bundle
hash lets promotion refuse any stale evidence drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_analysis.experiments.gates import GateEvaluation
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload

__all__ = [
    "REVIEW_PACKET_SCHEMA_VERSION",
    "ReviewPacket",
    "ReviewPacketLineage",
]

REVIEW_PACKET_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ReviewPacketLineage:
    """Experiment/candidate/fold/attempt identity carried by a bundle."""

    experiment_id: str
    candidate_id: str | None
    fold_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject empty or mistyped lineage identity."""
        if type(self.experiment_id) is not str or not self.experiment_id:
            raise ValueError("lineage experiment_id must be a non-empty string")
        if self.candidate_id is not None and (
            type(self.candidate_id) is not str or not self.candidate_id
        ):
            raise ValueError("lineage candidate_id must be a non-empty string or None")
        if type(self.fold_ids) is not tuple or not self.fold_ids:
            raise ValueError("lineage fold_ids must be a non-empty tuple")
        if type(self.attempt_ids) is not tuple or not self.attempt_ids:
            raise ValueError("lineage attempt_ids must be a non-empty tuple")

    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-ready lineage identity payload."""
        return {
            "experiment_id": self.experiment_id,
            "candidate_id": self.candidate_id,
            "fold_ids": list(self.fold_ids),
            "attempt_ids": list(self.attempt_ids),
        }


def _require_hash(value: object, field_name: str) -> ContentHash:
    if type(value) is not ContentHash:
        raise ValueError(f"{field_name} must be a ContentHash")
    return value


@dataclass(frozen=True, slots=True)
class ReviewPacket:
    """Immutable promotion evidence bundle; hash refuses stale evidence."""

    schema_version: int
    lineage: ReviewPacketLineage
    spec_hash: ContentHash
    resolved_spec_hash: ContentHash
    parameter_hash: ContentHash
    snapshot_hash: ContentHash
    registry_hash: ContentHash
    objective_payload_hash: ContentHash
    gate_evaluations: tuple[GateEvaluation, ...]
    comparison_payload_hash: ContentHash | None
    r1_impact_payload_hash: ContentHash | None
    selection_evidence_artifact_id: str | None
    holdout_claim_id: str | None
    candidate_rationale: str

    def __post_init__(self) -> None:
        """Validate schema version, reproduction hashes, and rationale."""
        if self.schema_version != REVIEW_PACKET_SCHEMA_VERSION:
            raise ValueError("unsupported review packet schema_version")
        for field_name in (
            "spec_hash",
            "resolved_spec_hash",
            "parameter_hash",
            "snapshot_hash",
            "registry_hash",
            "objective_payload_hash",
        ):
            _require_hash(getattr(self, field_name), field_name)
        if self.comparison_payload_hash is not None:
            _require_hash(self.comparison_payload_hash, "comparison_payload_hash")
        if self.r1_impact_payload_hash is not None:
            _require_hash(self.r1_impact_payload_hash, "r1_impact_payload_hash")
        if type(self.gate_evaluations) is not tuple:
            raise ValueError("gate_evaluations must be a tuple")
        if (
            type(self.candidate_rationale) is not str
            or not self.candidate_rationale
            or self.candidate_rationale != self.candidate_rationale.strip()
        ):
            raise ValueError("candidate_rationale must be a non-empty unpadded string")

    def canonical_payload(self) -> dict[str, object]:
        """Return the JSON-ready immutable bundle payload."""
        return {
            "schema_version": self.schema_version,
            "lineage": self.lineage.canonical_payload(),
            "spec_hash": str(self.spec_hash),
            "resolved_spec_hash": str(self.resolved_spec_hash),
            "parameter_hash": str(self.parameter_hash),
            "snapshot_hash": str(self.snapshot_hash),
            "registry_hash": str(self.registry_hash),
            "objective_payload_hash": str(self.objective_payload_hash),
            "gate_evaluations": [_gate_payload(item) for item in self.gate_evaluations],
            "comparison_payload_hash": _opt_hash(self.comparison_payload_hash),
            "r1_impact_payload_hash": _opt_hash(self.r1_impact_payload_hash),
            "selection_evidence_artifact_id": self.selection_evidence_artifact_id,
            "holdout_claim_id": self.holdout_claim_id,
            "candidate_rationale": self.candidate_rationale,
        }

    @property
    def bundle_hash(self) -> ContentHash:
        """Canonical hash over the complete bundle; refuses stale evidence."""
        return canonical_payload(self.canonical_payload()).content_hash


def _gate_payload(evaluation: GateEvaluation) -> dict[str, object]:
    return {
        "rule_id": evaluation.rule_id,
        "layer": evaluation.layer.value,
        "outcome": evaluation.outcome.value,
        "observed": evaluation.observed,
        "policy": evaluation.policy,
        "artifact_id": evaluation.artifact_id,
    }


def _opt_hash(value: ContentHash | None) -> str | None:
    return None if value is None else str(value)
