"""Typed factor-diagnostics identity and provenance reader tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest
from ditto_analysis.experiments import (
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
    SnapshotId,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._factor_diagnostics_evidence import (
    FactorDiagnosticsArtifactEvidence,
)
from ditto_application.processes.experiments.factor_diagnostics_reader import (
    FactorDiagnosticsReader,
    FactorDiagnosticsScope,
)
from ditto_features.evaluation.r3_diagnostics_identity import (
    R3FactorDiagnosticsProvenance,
)
from ditto_features.evaluation.report import project_r3_factor_diagnostics


@dataclass(frozen=True)
class _Source:
    evidence: tuple[FactorDiagnosticsArtifactEvidence, ...]

    def list_factor_diagnostics(
        self,
        scope: FactorDiagnosticsScope,
    ) -> tuple[FactorDiagnosticsArtifactEvidence, ...]:
        _ = scope
        return self.evidence


def _evidence() -> FactorDiagnosticsArtifactEvidence:
    window = DateWindow(date(2024, 1, 1), date(2024, 12, 31))
    projection = project_r3_factor_diagnostics(
        {"rank_ic": 0.08, "coverage": 0.97},
        provenance=R3FactorDiagnosticsProvenance(
            factor_id="momentum_1m",
            factor_version=1,
            evaluation_period=(window.start.isoformat(), window.end.isoformat()),
            dataset_id="factor_evaluation",
            catalog_snapshot_id="snapshot-r3",
            universe="a-share-r3",
            cost_bps=20.0,
        ),
    )
    return FactorDiagnosticsArtifactEvidence(
        experiment_id=ExperimentId("experiment-r3"),
        candidate_id=CandidateId("candidate-r3"),
        fold_id=FoldId("fold-r3"),
        snapshot_id=SnapshotId("snapshot-r3"),
        snapshot_hash=ContentHash("a" * 64),
        test_window=window,
        artifact_ref="diagnostic:momentum-1m:2024",
        projection=projection,
    )


def test_reader_projects_exact_scope_metrics_and_hashes() -> None:
    evidence = _evidence()
    reader = FactorDiagnosticsReader(
        source=_Source((evidence,)),
        expected_registry_hash="f" * 64,
    )

    view = reader.read(
        FactorDiagnosticsScope(
            factor_id="momentum_1m",
            snapshot_id="snapshot-r3",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            registry_hash="f" * 64,
        )
    )

    assert view.factor_id == "momentum_1m"
    assert view.snapshot_hash == "a" * 64
    assert view.metrics == {"coverage": 0.97, "rank_ic": 0.08}
    assert view.artifact_id == evidence.artifact_ref
    assert view.content_hash == str(evidence.artifact_hash)


def test_reader_rejects_registry_identity_mismatch() -> None:
    reader = FactorDiagnosticsReader(
        source=_Source((_evidence(),)),
        expected_registry_hash="f" * 64,
    )

    with pytest.raises(AppProcessError) as captured:
        reader.read(
            FactorDiagnosticsScope(
                factor_id="momentum_1m",
                snapshot_id="snapshot-r3",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                registry_hash="e" * 64,
            )
        )

    assert captured.value.details["code"] == "SNAPSHOT_IDENTITY_MISMATCH"
