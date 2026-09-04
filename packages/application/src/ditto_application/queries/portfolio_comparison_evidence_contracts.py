"""Pure application contracts for read-only portfolio comparison evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)

__all__ = [
    "PortfolioComparisonEvidenceIdentity",
    "PortfolioComparisonEvidenceQueryPort",
    "PortfolioComparisonEvidenceReadModel",
    "PortfolioScenarioEvidenceQueryPort",
    "PortfolioScenarioEvidenceReadModel",
    "PortfolioScenarioEvidenceRequest",
    "ScenarioBaselineKind",
]

type ScenarioBaselineKind = Literal["model", "paper", "manual"]


@dataclass(frozen=True, kw_only=True)
class PortfolioComparisonEvidenceIdentity:
    """Non-temporal portfolio identities a model may select."""

    strategy_id: str
    model_portfolio_id: str
    paper_account_id: str
    manual_account_id: str
    paper_session_id: str


@dataclass(frozen=True, kw_only=True)
class PortfolioScenarioEvidenceRequest:
    """User scenario intent without proposed target weights or temporal authority."""

    identity: PortfolioComparisonEvidenceIdentity
    baseline_kind: ScenarioBaselineKind
    excluded_instrument_ids: frozenset[int]
    max_position_weight: Decimal
    cash_reserve_weight: Decimal
    market_shock: float = 0.0
    industry_shocks: Mapping[str, float] | None = None


@dataclass(frozen=True, kw_only=True)
class PortfolioComparisonEvidenceReadModel:
    """Sealed-ready comparison values and provenance for Agent consumption."""

    identity: PortfolioComparisonEvidenceIdentity
    as_of: str
    valuation_snapshot_id: str
    source_snapshot_set_id: str
    source_snapshot_ids: tuple[str, ...]
    temporal_context: EvidenceTemporalContext
    payload: EvidencePayloadReadModel
    artifact_refs: tuple[EvidenceArtifactReference, ...]
    lineage: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class PortfolioScenarioEvidenceReadModel:
    """Sealed-ready read-only scenario values and exact comparison provenance."""

    identity: PortfolioComparisonEvidenceIdentity
    baseline_kind: ScenarioBaselineKind
    as_of: str
    valuation_snapshot_id: str
    source_snapshot_set_id: str
    source_snapshot_ids: tuple[str, ...]
    temporal_context: EvidenceTemporalContext
    payload: EvidencePayloadReadModel
    artifact_refs: tuple[EvidenceArtifactReference, ...]
    lineage: tuple[str, ...]


@runtime_checkable
class PortfolioComparisonEvidenceQueryPort(Protocol):
    """Leaf query used by the read-only Agent comparison tool."""

    def get_comparison_evidence(
        self,
        *,
        identity: PortfolioComparisonEvidenceIdentity,
        context: EvidenceTemporalContext,
    ) -> PortfolioComparisonEvidenceReadModel:
        """Return host-bound comparison evidence."""
        ...


@runtime_checkable
class PortfolioScenarioEvidenceQueryPort(Protocol):
    """Leaf preview used by the read-only Agent scenario tool."""

    def preview_scenario(
        self,
        *,
        request: PortfolioScenarioEvidenceRequest,
        context: EvidenceTemporalContext,
    ) -> PortfolioScenarioEvidenceReadModel:
        """Return a deterministic preview without applying its target."""
        ...
