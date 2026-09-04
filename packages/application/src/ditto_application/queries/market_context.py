"""Exact PIT market-context aggregation and consumer-facing read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_features.market_context.contracts import (
    MarketRegimeFeatureSet,
    MarketRegimeInput,
)

from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError

__all__ = [
    "MarketContextFacade",
    "MarketContextFacts",
    "MarketContextImpact",
    "MarketContextMetric",
    "MarketContextQueryPort",
    "MarketContextQueryService",
    "MarketContextRequest",
    "MarketContextSourcePort",
    "MarketContextView",
    "MarketRegimeEvaluator",
    "UnavailableMarketContextSource",
]

type ContextStatus = Literal["ready", "degraded", "blocked"]
type ImpactDirection = Literal["supportive", "pressuring", "neutral"]


@dataclass(frozen=True, slots=True)
class MarketContextRequest:
    """API-facing exact PIT identity before dataset snapshots are resolved."""

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketContextMetric:
    """One observed market or macro fact with direct evidence lineage."""

    name: str
    category: Literal["a_share", "style", "global", "rates", "fx", "commodity", "macro"]
    value: float
    unit: str
    trend: Literal["rising", "falling", "flat", "mixed", "unknown"]
    freshness: Literal["fresh", "stale", "missing"]
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class MarketContextFacts:
    """PIT-bound facts loaded by a data-backed application adapter."""

    regime_input: MarketRegimeInput
    metrics: tuple[MarketContextMetric, ...]
    data_conflicts: tuple[str, ...]
    uncertainties: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketContextImpact:
    """One deterministic downstream implication of the regime conclusion."""

    target_domain: Literal["industry", "selection", "portfolio", "risk"]
    target: str
    direction: ImpactDirection
    rationale_driver: str


@dataclass(frozen=True, slots=True)
class MarketContextDriverView:
    """Application projection of one feature-owned driver attribution."""

    name: str
    category: str
    contribution: float
    direction: ImpactDirection


@dataclass(frozen=True, slots=True)
class MarketContextView:
    """Shared Markets, Today, Selection, Portfolio, and Agent read model."""

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    source_snapshot_set_id: str
    status: ContextStatus
    feature_set_id: str
    feature_version: str
    regime_label: Literal["risk_on", "balanced", "risk_off"] | None
    regime_score: float | None
    drivers: tuple[MarketContextDriverView, ...]
    metrics: tuple[MarketContextMetric, ...]
    impacts: tuple[MarketContextImpact, ...]
    missing_inputs: tuple[str, ...]
    data_conflicts: tuple[str, ...]
    uncertainties: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@runtime_checkable
class MarketContextSourcePort(Protocol):
    """Load normalized facts from the exact data PIT context."""

    def load(self, context: PITQueryContext) -> MarketContextFacts:
        """Return facts whose time and source identities exactly match context."""
        ...


@runtime_checkable
class MarketRegimeEvaluator(Protocol):
    """Evaluate feature-owned deterministic market-regime formulas."""

    def evaluate(self, value: MarketRegimeInput) -> MarketRegimeFeatureSet:
        """Return one versioned deterministic feature set."""
        ...


@runtime_checkable
class MarketContextQueryPort(Protocol):
    """Read a shared market context for one exact PIT identity."""

    def get_context(self, context: PITQueryContext) -> MarketContextView:
        """Return a ready, degraded, or blocked context without latest fallback."""
        ...


class UnavailableMarketContextSource:
    """Safe default until an exact immutable-payload adapter is configured."""

    def load(self, context: PITQueryContext) -> MarketContextFacts:
        """Preserve PIT identity while refusing to synthesize unavailable facts."""
        return MarketContextFacts(
            regime_input=MarketRegimeInput(
                as_of=context.as_of,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_ids=context.source_snapshot_ids,
                advancing_count=None,
                declining_count=None,
                universe_count=None,
                benchmark_return_20d=None,
                small_cap_return_20d=None,
                large_cap_return_20d=None,
                realized_volatility_20d=None,
                global_return_1d=None,
                macro_surprise_score=None,
                macro_trend_score=None,
            ),
            metrics=(),
            data_conflicts=(),
            uncertainties=("market_context_source_unavailable",),
        )


def _dataset_snapshots(
    snapshots: tuple[ProviderSnapshot, ...],
) -> tuple[DatasetSnapshot, ...]:
    grouped: dict[str, list[ProviderSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.dataset_id, []).append(snapshot)

    resolved: list[DatasetSnapshot] = []
    for dataset_id, values in grouped.items():
        schema_versions = {value.schema_version for value in values}
        if len(schema_versions) != 1:
            raise AppQueryError(
                f"market context dataset {dataset_id!r} has mixed schema versions"
            )
        resolved.append(
            DatasetSnapshot(
                dataset_id=dataset_id,
                dataset_version=next(iter(schema_versions)),
                source_snapshot_ids=tuple(value.snapshot_id for value in values),
                created_at=max(value.created_at for value in values),
            )
        )
    return tuple(resolved)


class MarketContextFacade:
    """Resolve immutable provider evidence and delegate the aggregate query."""

    def __init__(
        self,
        *,
        snapshot_reader: ProviderSnapshotReader,
        query: MarketContextQueryPort,
    ) -> None:
        self._snapshot_reader = snapshot_reader
        self._query = query

    def get_context(self, request: MarketContextRequest) -> MarketContextView:
        """Read only the requested snapshots; never substitute a latest snapshot."""
        if not request.source_snapshot_ids or len(
            set(request.source_snapshot_ids)
        ) != len(request.source_snapshot_ids):
            raise AppQueryError(
                "market context requires unique explicit source snapshot IDs"
            )
        snapshots: list[ProviderSnapshot] = []
        for snapshot_id in request.source_snapshot_ids:
            snapshot = self._snapshot_reader.get_snapshot(snapshot_id)
            if snapshot is None or snapshot.snapshot_id != snapshot_id:
                raise AppQueryError(
                    f"market context source snapshot {snapshot_id!r} was not found"
                )
            if snapshot.created_at > request.knowledge_cutoff:
                message = f"market context source snapshot {snapshot_id!r}"
                message += " is not visible at knowledge_cutoff="
                message += request.knowledge_cutoff.isoformat()
                raise AppQueryError(message)
            snapshots.append(snapshot)
        try:
            context = PITQueryContext(
                as_of=request.as_of,
                knowledge_cutoff=request.knowledge_cutoff,
                publication_cutoff=request.publication_cutoff,
                source_snapshots=_dataset_snapshots(tuple(snapshots)),
            )
        except ValueError as error:
            raise AppQueryError(str(error)) from error
        return self._query.get_context(context)


def _impacts(result: MarketRegimeFeatureSet) -> tuple[MarketContextImpact, ...]:
    if result.status == "blocked" or result.label is None:
        return ()
    if result.label == "risk_on":
        return (
            MarketContextImpact("industry", "cyclical", "supportive", "breadth"),
            MarketContextImpact("selection", "momentum", "supportive", "trend"),
            MarketContextImpact("portfolio", "equity_beta", "supportive", "trend"),
            MarketContextImpact(
                "risk",
                "volatility_budget",
                "supportive",
                "volatility",
            ),
        )
    if result.label == "risk_off":
        return (
            MarketContextImpact("industry", "defensive", "supportive", "volatility"),
            MarketContextImpact("selection", "high_beta", "pressuring", "trend"),
            MarketContextImpact("portfolio", "equity_beta", "pressuring", "trend"),
            MarketContextImpact("risk", "drawdown_guard", "pressuring", "volatility"),
        )
    return (
        MarketContextImpact("industry", "broad_market", "neutral", "breadth"),
        MarketContextImpact("selection", "factor_mix", "neutral", "trend"),
        MarketContextImpact("portfolio", "equity_beta", "neutral", "trend"),
        MarketContextImpact("risk", "volatility_budget", "neutral", "volatility"),
    )


class MarketContextQueryService:
    """Aggregate data-backed facts and feature-owned conclusions."""

    def __init__(
        self,
        source: MarketContextSourcePort,
        evaluator: MarketRegimeEvaluator,
    ) -> None:
        self._source = source
        self._evaluator = evaluator

    def get_context(self, context: PITQueryContext) -> MarketContextView:
        """Return a context only when source facts preserve the exact PIT identity."""
        facts = self._source.load(context)
        regime_input = facts.regime_input
        if (
            regime_input.as_of != context.as_of
            or regime_input.knowledge_cutoff != context.knowledge_cutoff
            or regime_input.publication_cutoff != context.publication_cutoff
            or regime_input.source_snapshot_ids != context.source_snapshot_ids
        ):
            raise AppQueryError("market context source PIT context drift")
        result = self._evaluator.evaluate(regime_input)
        evidence_refs = tuple(
            dict.fromkeys(metric.evidence_ref for metric in facts.metrics)
        )
        status: ContextStatus = result.status
        if status == "ready" and (facts.data_conflicts or facts.uncertainties):
            status = "degraded"
        snapshot_set_id = aggregate_source_snapshot_ids(context.source_snapshot_ids)
        if snapshot_set_id is None:
            raise AppQueryError("market context source snapshot set is empty")
        return MarketContextView(
            as_of=context.as_of,
            knowledge_cutoff=context.knowledge_cutoff,
            publication_cutoff=context.publication_cutoff,
            source_snapshot_ids=context.source_snapshot_ids,
            source_snapshot_set_id=snapshot_set_id,
            status=status,
            feature_set_id=result.feature_set_id,
            feature_version=result.feature_version,
            regime_label=result.label,
            regime_score=result.score,
            drivers=tuple(
                MarketContextDriverView(
                    name=driver.name,
                    category=driver.category,
                    contribution=driver.contribution,
                    direction=driver.direction,
                )
                for driver in result.drivers
            ),
            metrics=facts.metrics,
            impacts=_impacts(result),
            missing_inputs=result.missing_inputs,
            data_conflicts=facts.data_conflicts,
            uncertainties=facts.uncertainties,
            evidence_refs=evidence_refs,
        )
