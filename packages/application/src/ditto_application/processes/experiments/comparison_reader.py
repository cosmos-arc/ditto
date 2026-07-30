"""
Read-only candidate-comparison view for the research control-plane surface.

The persisted walk-forward evidence is assembled by
:class:`WalkForwardEvidenceAssembler` during review-packet collection. This
reader reuses that exact read path (snapshot -> status events -> preflight
detail -> manifest -> assemble) but stops before holdout/selection and review
publication, so a candidate comparison is available as soon as walk-forward
folds exist. The result is projected into a plain application read model so
API routes never touch analysis types.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ditto_analysis.experiments import ExperimentId, ExperimentReaderProtocol

from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
    read_unique_preflight_detail,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
)

__all__ = ["CandidateComparisonView", "ExperimentComparisonReader"]


@dataclass(frozen=True, slots=True)
class CandidateComparisonView:
    """Application read model for one experiment's candidate comparison."""

    experiment_id: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ExperimentComparisonReader:
    """Assemble and return one experiment's candidate comparison as a plain view."""

    scheduler_store: ExperimentSchedulerStore
    reader: ExperimentReaderProtocol
    walk_forward_assembler: WalkForwardEvidenceAssembler

    def load_comparison(self, experiment_id: str) -> CandidateComparisonView | None:
        """Return the candidate comparison, or ``None`` if the experiment is absent."""
        typed_id = ExperimentId(experiment_id)
        if self.reader.get_experiment_projection(typed_id) is None:
            return None
        snapshot = self.scheduler_store.load_snapshot(typed_id)
        events = self.reader.list_status_events(typed_id)
        detail = read_unique_preflight_detail(events, typed_id)
        manifest = project_snapshot_manifest(detail)
        collected = self.walk_forward_assembler.assemble(snapshot, manifest)
        return CandidateComparisonView(
            experiment_id=experiment_id,
            payload=MappingProxyType(collected.comparison.canonical_payload()),
        )
