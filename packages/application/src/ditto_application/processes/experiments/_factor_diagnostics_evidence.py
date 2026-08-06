"""Application-owned lineage envelope for R3 factor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_analysis.experiments import (
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
    SnapshotId,
    canonical_payload,
)
from ditto_features.evaluation.report import (
    R3FactorDiagnosticsProjection,
)

from ditto_application.processes.experiments._evidence_values import (
    canonical_text,
    comparison_error,
)

_FACTOR_DIAGNOSTICS_ARTIFACT_SCHEMA_ID = "ditto.r3.factor-diagnostics-evidence"
_FACTOR_DIAGNOSTICS_ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class FactorDiagnosticsArtifactEvidence:
    """Bind a features-owned projection to exact application fold lineage."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId
    snapshot_id: SnapshotId
    snapshot_hash: ContentHash
    test_window: DateWindow
    artifact_ref: str
    projection: R3FactorDiagnosticsProjection
    artifact_hash: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        """Validate exact lineage and derive the complete envelope hash."""
        typed = (
            (self.experiment_id, ExperimentId),
            (self.candidate_id, CandidateId),
            (self.fold_id, FoldId),
            (self.snapshot_id, SnapshotId),
            (self.snapshot_hash, ContentHash),
            (self.test_window, DateWindow),
            (self.projection, R3FactorDiagnosticsProjection),
        )
        if any(type(value) is not expected for value, expected in typed):
            comparison_error("invalid_factor_diagnostics_artifact")
        canonical_text(self.artifact_ref, "factor_diagnostics_artifact_ref")
        provenance = self.projection.provenance
        if provenance.evaluation_period != (
            self.test_window.start.isoformat(),
            self.test_window.end.isoformat(),
        ) or provenance.catalog_snapshot_id != str(self.snapshot_id):
            comparison_error("factor_diagnostic_identity_drift")
        object.__setattr__(
            self,
            "artifact_hash",
            canonical_payload(self.canonical_payload()).content_hash,
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete versioned diagnostics lineage preimage."""
        return {
            "artifact_ref": self.artifact_ref,
            "artifact_schema": {
                "id": _FACTOR_DIAGNOSTICS_ARTIFACT_SCHEMA_ID,
                "version": _FACTOR_DIAGNOSTICS_ARTIFACT_SCHEMA_VERSION,
            },
            "candidate_id": str(self.candidate_id),
            "experiment_id": str(self.experiment_id),
            "factor_projection": {
                "computed_metrics": list(self.projection.computed_metrics),
                "content_hash": self.projection.content_hash,
                "provenance": self.projection.provenance.canonical_payload(),
            },
            "fold_id": str(self.fold_id),
            "snapshot_hash": str(self.snapshot_hash),
            "snapshot_id": str(self.snapshot_id),
            "test_window": {
                "end": self.test_window.end.isoformat(),
                "start": self.test_window.start.isoformat(),
            },
        }
