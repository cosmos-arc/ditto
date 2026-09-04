"""Application-owned immutable read models for selection transports and Agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_kernel.identity import InstrumentId
from ditto_strategy.industry_rotation.contracts import IndustryRotationSnapshot
from ditto_strategy.selection.contracts import SelectionRun

__all__ = [
    "IndustryRotationContributionView",
    "IndustryRotationRankView",
    "IndustryRotationView",
    "SelectionCandidateView",
    "SelectionExclusionView",
    "SelectionFactorContributionView",
    "SelectionRunView",
    "SelectionWorkspaceReceiptView",
    "to_industry_rotation_view",
    "to_selection_run_view",
    "to_selection_workspace_receipt_view",
]


@dataclass(frozen=True, slots=True)
class IndustryRotationContributionView:
    """One additive industry score component."""

    metric: str
    value: float | None
    weight: float
    contribution: float


@dataclass(frozen=True, slots=True)
class IndustryRotationRankView:
    """One exact ranked industry."""

    industry_id: str
    industry_name: str
    rank: int
    score: float
    contributions: tuple[IndustryRotationContributionView, ...]
    missing_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IndustryRotationView:
    """Exact industry snapshot read model."""

    snapshot_id: str
    input_hash: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    market_context_feature_set_id: str | None
    membership_version: str
    algorithm_version: str
    status: str
    rankings: tuple[IndustryRotationRankView, ...]
    missing_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionFactorContributionView:
    """One additive selected-instrument score component."""

    factor_name: str
    value: float
    weight: float
    contribution: float


@dataclass(frozen=True, slots=True)
class SelectionCandidateView:
    """One selected candidate and exact factor attribution."""

    instrument_id: InstrumentId
    instrument_name: str
    industry_id: str | None
    rank: int
    score: float
    factor_contributions: tuple[SelectionFactorContributionView, ...]


@dataclass(frozen=True, slots=True)
class SelectionExclusionView:
    """One exact why-out record."""

    instrument_id: InstrumentId
    instrument_name: str
    reason_code: str
    stage: str
    detail: str


@dataclass(frozen=True, slots=True)
class SelectionRunView:
    """Exact saved SelectionRun projected without exposing strategy internals."""

    run_id: str
    input_hash: str
    spec_hash: str
    asset_kind: str
    spec_id: str
    spec_version: str
    seed: int
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    universe_snapshot_id: str
    industry_rotation_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...]
    status: str
    candidates: tuple[SelectionCandidateView, ...]
    exclusions: tuple[SelectionExclusionView, ...]
    missing_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionWorkspaceReceiptView:
    """Public result for one rotation plus selection mutation."""

    industry_rotation: IndustryRotationView
    selection_run: SelectionRunView


def to_industry_rotation_view(value: IndustryRotationSnapshot) -> IndustryRotationView:
    """Project a strategy snapshot into an application read model."""
    return IndustryRotationView(
        snapshot_id=value.snapshot_id,
        input_hash=value.input_hash,
        as_of=value.as_of,
        knowledge_cutoff=value.knowledge_cutoff,
        publication_cutoff=value.publication_cutoff,
        source_snapshot_ids=value.source_snapshot_ids,
        market_context_feature_set_id=value.market_context_feature_set_id,
        membership_version=value.membership_version,
        algorithm_version=value.algorithm_version,
        status=value.status.value,
        rankings=tuple(
            IndustryRotationRankView(
                industry_id=item.industry_id,
                industry_name=item.industry_name,
                rank=item.rank,
                score=item.score,
                contributions=tuple(
                    IndustryRotationContributionView(
                        metric=contribution.metric,
                        value=contribution.value,
                        weight=contribution.weight,
                        contribution=contribution.contribution,
                    )
                    for contribution in item.contributions
                ),
                missing_inputs=item.missing_inputs,
            )
            for item in value.rankings
        ),
        missing_inputs=value.missing_inputs,
    )


def to_selection_run_view(value: SelectionRun) -> SelectionRunView:
    """Project an exact saved run into an application read model."""
    return SelectionRunView(
        run_id=value.run_id,
        input_hash=value.input_hash,
        spec_hash=value.spec_hash,
        asset_kind=value.asset_kind.value,
        spec_id=value.spec_id,
        spec_version=value.spec_version,
        seed=value.seed,
        as_of=value.as_of,
        knowledge_cutoff=value.knowledge_cutoff,
        publication_cutoff=value.publication_cutoff,
        universe_snapshot_id=value.universe_snapshot_id,
        industry_rotation_snapshot_id=value.industry_rotation_snapshot_id,
        source_snapshot_ids=value.source_snapshot_ids,
        status=value.status.value,
        candidates=tuple(
            SelectionCandidateView(
                instrument_id=item.instrument_id,
                instrument_name=item.instrument_name,
                industry_id=item.industry_id,
                rank=item.rank,
                score=item.score,
                factor_contributions=tuple(
                    SelectionFactorContributionView(
                        factor_name=factor.factor_name,
                        value=factor.value,
                        weight=factor.weight,
                        contribution=factor.contribution,
                    )
                    for factor in item.factor_contributions
                ),
            )
            for item in value.candidates
        ),
        exclusions=tuple(
            SelectionExclusionView(
                instrument_id=item.instrument_id,
                instrument_name=item.instrument_name,
                reason_code=item.reason_code.value,
                stage=item.stage,
                detail=item.detail,
            )
            for item in value.exclusions
        ),
        missing_inputs=value.missing_inputs,
    )


def to_selection_workspace_receipt_view(
    rotation: IndustryRotationSnapshot,
    selection_run: SelectionRun,
) -> SelectionWorkspaceReceiptView:
    """Project both exact artifacts returned by the mutation process."""
    return SelectionWorkspaceReceiptView(
        industry_rotation=to_industry_rotation_view(rotation),
        selection_run=to_selection_run_view(selection_run),
    )
