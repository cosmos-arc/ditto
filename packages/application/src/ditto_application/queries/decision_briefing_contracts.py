"""Pure application contracts for post-V3 shadow briefing evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)

__all__ = [
    "DecisionBriefingEvidenceQueryPort",
    "DecisionBriefingEvidenceReadModel",
]


@dataclass(frozen=True, slots=True)
class DecisionBriefingEvidenceReadModel:
    """Exact V3 evidence for shadow explanation, including blocked reports."""

    strategy_id: str
    strategy_version: str
    trade_date: str
    account_id: str
    sleeve_id: str
    readiness: Literal["ready", "review", "blocked"]
    blocking_reasons: tuple[str, ...]
    temporal_context: EvidenceTemporalContext
    payload: EvidencePayloadReadModel
    artifact_refs: tuple[EvidenceArtifactReference, ...]
    lineage: tuple[str, ...]


class DecisionBriefingEvidenceQueryPort(Protocol):
    """Consumer-owned read port for one exact post-V3 shadow briefing."""

    def get_briefing_evidence(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        trade_date: str,
        account_id: str,
        sleeve_id: str,
        context: EvidenceTemporalContext,
    ) -> DecisionBriefingEvidenceReadModel:
        """Read ready, review, or blocked V3 evidence with exact provenance."""
        ...
