"""Exact PIT orchestration for deterministic technical analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisInput,
    TechnicalAnalysisSnapshot,
    TechnicalAnalysisSpec,
    TechnicalBar,
    TechnicalTimeframe,
)
from ditto_kernel.identity import InstrumentId

from ditto_application.exceptions import AppQueryError

__all__ = [
    "TechnicalAnalysisEvaluator",
    "TechnicalAnalysisFacade",
    "TechnicalAnalysisQueryPort",
    "TechnicalAnalysisQueryService",
    "TechnicalAnalysisRequest",
    "TechnicalAnalysisSourcePort",
    "TechnicalAnalysisSpecDraft",
    "UnavailableTechnicalAnalysisSource",
]

type TechnicalTimeframeDraft = Literal["daily", "weekly"]


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisSpecDraft:
    """Application-facing parameter set before feature validation."""

    spec_id: str
    spec_version: str
    timeframes: tuple[TechnicalTimeframeDraft, ...]
    return_window: int = 20
    trend_window: int = 20
    slope_window: int = 5
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_window: int = 14
    volatility_window: int = 20
    volume_window: int = 20
    donchian_window: int = 20
    support_resistance_window: int = 60
    algorithm_version: str = "technical-analysis.v1"


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisRequest:
    """Public exact-snapshot request for one instrument."""

    instrument_id: InstrumentId
    instrument_name: str
    instrument_code: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    spec: TechnicalAnalysisSpecDraft
    selection_run_id: str | None = None
    research_case_id: str | None = None
    portfolio_snapshot_id: str | None = None


@runtime_checkable
class TechnicalAnalysisSourcePort(Protocol):
    """Load source-bound bars for one exact PIT context."""

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        """Return raw bars without substituting a latest dataset snapshot."""
        ...


@runtime_checkable
class TechnicalAnalysisEvaluator(Protocol):
    """Evaluate the feature-owned deterministic formulas."""

    def analyze(self, value: TechnicalAnalysisInput) -> TechnicalAnalysisSnapshot:
        """Return one content-addressed technical snapshot."""
        ...


@runtime_checkable
class TechnicalAnalysisQueryPort(Protocol):
    """Compute one technical snapshot from a resolved PIT context."""

    def get_snapshot(
        self,
        context: PITQueryContext,
        request: TechnicalAnalysisRequest,
    ) -> TechnicalAnalysisSnapshot:
        """Return only results derived from the exact requested source snapshots."""
        ...


class UnavailableTechnicalAnalysisSource:
    """Fail-closed source used when no retained-payload adapter is configured."""

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        """Return no bars; the feature service exposes explicit warm-up states."""
        del context, instrument_id, instrument_code
        return ()


def _spec(value: TechnicalAnalysisSpecDraft) -> TechnicalAnalysisSpec:
    return TechnicalAnalysisSpec(
        spec_id=value.spec_id,
        spec_version=value.spec_version,
        algorithm_version=value.algorithm_version,
        timeframes=tuple(TechnicalTimeframe(item) for item in value.timeframes),
        return_window=value.return_window,
        trend_window=value.trend_window,
        slope_window=value.slope_window,
        rsi_window=value.rsi_window,
        macd_fast=value.macd_fast,
        macd_slow=value.macd_slow,
        macd_signal=value.macd_signal,
        atr_window=value.atr_window,
        volatility_window=value.volatility_window,
        volume_window=value.volume_window,
        donchian_window=value.donchian_window,
        support_resistance_window=value.support_resistance_window,
    )


class TechnicalAnalysisQueryService:
    """Coordinate a narrow data adapter with the feature-owned evaluator."""

    def __init__(
        self,
        source: TechnicalAnalysisSourcePort,
        evaluator: TechnicalAnalysisEvaluator,
    ) -> None:
        self._source = source
        self._evaluator = evaluator

    def get_snapshot(
        self,
        context: PITQueryContext,
        request: TechnicalAnalysisRequest,
    ) -> TechnicalAnalysisSnapshot:
        """Build the feature input from exact source facts and evaluate it."""
        if (
            request.as_of != context.as_of
            or request.knowledge_cutoff != context.knowledge_cutoff
            or request.publication_cutoff != context.publication_cutoff
            or request.source_snapshot_ids != context.source_snapshot_ids
        ):
            raise AppQueryError("technical analysis PIT context drift")
        try:
            bars = self._source.load(
                context,
                instrument_id=request.instrument_id,
                instrument_code=request.instrument_code,
            )
            return self._evaluator.analyze(
                TechnicalAnalysisInput(
                    instrument_id=request.instrument_id,
                    instrument_name=request.instrument_name,
                    as_of=context.as_of,
                    knowledge_cutoff=context.knowledge_cutoff,
                    publication_cutoff=context.publication_cutoff,
                    source_snapshot_ids=context.source_snapshot_ids,
                    spec=_spec(request.spec),
                    bars=bars,
                    selection_run_id=request.selection_run_id,
                    research_case_id=request.research_case_id,
                    portfolio_snapshot_id=request.portfolio_snapshot_id,
                )
            )
        except ValueError as error:
            raise AppQueryError(str(error)) from error


def _dataset_snapshots(
    snapshots: tuple[ProviderSnapshot, ...],
) -> tuple[DatasetSnapshot, ...]:
    grouped: dict[str, list[ProviderSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.dataset_id, []).append(snapshot)
    resolved: list[DatasetSnapshot] = []
    for dataset_id, values in grouped.items():
        versions = {item.schema_version for item in values}
        if len(versions) != 1:
            raise AppQueryError(
                f"technical analysis dataset {dataset_id!r} has mixed schema versions"
            )
        resolved.append(
            DatasetSnapshot(
                dataset_id=dataset_id,
                dataset_version=next(iter(versions)),
                source_snapshot_ids=tuple(item.snapshot_id for item in values),
                created_at=max(item.created_at for item in values),
            )
        )
    return tuple(resolved)


class TechnicalAnalysisFacade:
    """Resolve immutable provider evidence before evaluating indicators."""

    def __init__(
        self,
        *,
        snapshot_reader: ProviderSnapshotReader,
        query: TechnicalAnalysisQueryPort,
    ) -> None:
        self._snapshot_reader = snapshot_reader
        self._query = query

    def get_snapshot(
        self,
        request: TechnicalAnalysisRequest,
    ) -> TechnicalAnalysisSnapshot:
        """Read every exact snapshot identity and never fall back to latest."""
        if not request.source_snapshot_ids or len(
            set(request.source_snapshot_ids)
        ) != len(request.source_snapshot_ids):
            raise AppQueryError(
                "technical analysis requires unique explicit source snapshot IDs"
            )
        if not request.instrument_code or request.instrument_code.strip() != (
            request.instrument_code
        ):
            raise AppQueryError("technical analysis instrument code is invalid")
        snapshots: list[ProviderSnapshot] = []
        for snapshot_id in request.source_snapshot_ids:
            snapshot = self._snapshot_reader.get_snapshot(snapshot_id)
            if snapshot is None or snapshot.snapshot_id != snapshot_id:
                raise AppQueryError(
                    f"technical analysis source snapshot {snapshot_id!r} was not found"
                )
            if snapshot.created_at > request.knowledge_cutoff:
                raise AppQueryError(
                    f"technical analysis source snapshot {snapshot_id!r} is not visible"
                )
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
        return self._query.get_snapshot(context, request)
