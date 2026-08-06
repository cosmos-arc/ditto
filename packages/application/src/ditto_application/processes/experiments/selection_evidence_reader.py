"""
Read-only selection-evidence view for the research control-plane surface.

The review packet only persists the ``selection_evidence_artifact_id`` pointer.
This reader resolves the content-addressed selection ledger for one experiment
by delegating to :class:`DurableSelectionEvidenceService` (which rebuilds and
verifies the typed ledger against the persisted artifact hash) and projects it
into a plain application read model so API routes never touch analysis types.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from ditto_analysis.experiments import ExperimentId, ExperimentReaderProtocol

from ditto_application.processes.experiments._selection_evidence_artifact import (
    DurableSelectionEvidenceService,
)

__all__ = ["ExperimentSelectionEvidenceReader", "SelectionEvidenceView"]

_SELECTION_EVIDENCE_PATH = "experiments/{experiment_id}/selection-evidence.json"


@dataclass(frozen=True, slots=True)
class SelectionEvidenceView:
    """Application read model for one experiment's published selection evidence."""

    artifact_id: str
    experiment_id: str
    content_hash: str
    byte_size: int
    is_pinned: bool
    created_at: datetime
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ExperimentSelectionEvidenceReader:
    """Resolve and verify one experiment's selection evidence as a plain view."""

    reader: ExperimentReaderProtocol
    selection_service: DurableSelectionEvidenceService

    def load_view(self, experiment_id: str) -> SelectionEvidenceView | None:
        """Return the verified selection-evidence view, or ``None`` if absent."""
        typed_id = ExperimentId(experiment_id)
        record = self.reader.get_artifact_by_relative_path(
            _SELECTION_EVIDENCE_PATH.format(experiment_id=typed_id)
        )
        if record is None:
            return None
        published = self.selection_service.read_selection_evidence(
            typed_id, record.content_hash
        )
        return SelectionEvidenceView(
            artifact_id=record.artifact_id,
            experiment_id=str(record.experiment_id),
            content_hash=str(record.content_hash),
            byte_size=record.byte_size,
            is_pinned=record.is_pinned,
            created_at=record.created_at,
            payload=MappingProxyType(published.ledger.canonical_payload()),
        )
