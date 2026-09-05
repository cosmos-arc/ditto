"""Exact composition probes for OPS-09 workstation performance evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ditto_application.queries.data_products import DataProductsQueryFacade
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
    PortfolioComparisonSource,
)
from ditto_data.catalog.certification import (
    CertificationReviewEvent,
    DatasetCertificationReport,
)
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisInput,
    TechnicalAnalysisSpec,
    TechnicalBar,
    TechnicalTimeframe,
)
from ditto_features.technical_analysis.service import TechnicalAnalysisService
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.portfolio_comparison import (
    PortfolioHoldingInput,
    PortfolioValuationInput,
)
from ditto_strategy.selection.contracts import (
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    StockSelectionSpec,
)
from ditto_strategy.selection.pipeline import SelectionPipeline

from ditto_apps.operations.workstation_performance import PerformanceCase


def default_workstation_performance_cases() -> tuple[PerformanceCase, ...]:
    """Build the four deterministic operations named by OPS-09."""
    read_models = DataProductsQueryFacade(_EmptyCertificationReader())
    selection_input = _selection_input()
    technical_input = _technical_input()
    comparison_query, comparison_request = _comparison_operation()
    return (
        PerformanceCase(
            "read_models",
            lambda: read_models.list_products(profile="r2-modern-a-share-v1"),
            threshold_ms=250.0,
        ),
        PerformanceCase(
            "selection",
            lambda: SelectionPipeline().run(selection_input),
            threshold_ms=1_000.0,
        ),
        PerformanceCase(
            "technical_analysis",
            lambda: TechnicalAnalysisService().analyze(technical_input),
            threshold_ms=1_000.0,
        ),
        PerformanceCase(
            "portfolio_comparison",
            lambda: comparison_query.get(comparison_request),
            threshold_ms=250.0,
        ),
    )


class _EmptyCertificationReader:
    def get_report(self, report_id: str) -> DatasetCertificationReport | None:
        del report_id
        return None

    def get_active_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport | None:
        del dataset_id, profile
        return None

    def list_reports(
        self,
        dataset_id: str,
        profile: str,
    ) -> tuple[DatasetCertificationReport, ...]:
        del dataset_id, profile
        return ()

    def list_events(self, report_id: str) -> tuple[CertificationReviewEvent, ...]:
        del report_id
        return ()


def _selection_input() -> SelectionInputBundle:
    as_of = datetime(2026, 8, 31, 7, tzinfo=UTC)
    weights = (
        SelectionFactorWeight(name="quality", weight=0.4),
        SelectionFactorWeight(name="momentum", weight=0.6),
    )
    instruments = tuple(
        SelectionInstrumentInput(
            instrument_id=InstrumentId(600000 + index),
            instrument_name=f"Instrument {index}",
            industry_id=f"80{index % 31:04d}",
            factor_values=(
                SelectionFactorValue(name="quality", value=(index % 17) / 17),
                SelectionFactorValue(name="momentum", value=(index % 29) / 29),
            ),
            average_turnover=100_000_000.0 + index,
            is_st=False,
            is_suspended=False,
            listing_days=500,
            limit_state=SelectionLimitState.NORMAL,
            tracking_error=None,
        )
        for index in range(500)
    )
    return SelectionInputBundle(
        as_of=as_of,
        knowledge_cutoff=as_of,
        publication_cutoff=as_of,
        universe_snapshot_id="universe:sha256:performance",
        industry_rotation_snapshot_id="industry:sha256:performance",
        source_snapshot_ids=("market:sha256:performance",),
        spec=StockSelectionSpec(
            spec_id="performance-stock",
            spec_version="1",
            top_k=25,
            min_average_turnover=20_000_000.0,
            min_listing_days=120,
            factor_weights=weights,
        ),
        seed=17,
        instruments=instruments,
    )


def _technical_input() -> TechnicalAnalysisInput:
    start = datetime(2025, 12, 1, 7, tzinfo=UTC)
    bars = tuple(
        TechnicalBar(
            occurred_at=start + timedelta(days=index),
            knowledge_at=start + timedelta(days=index, minutes=5),
            publication_at=start + timedelta(days=index),
            source_snapshot_id="market:sha256:performance",
            open=100.0 + index * 0.1,
            high=102.0 + index * 0.1,
            low=99.0 + index * 0.1,
            close=101.0 + index * 0.1,
            volume=1_000_000.0 + index,
            turnover=(101.0 + index * 0.1) * (1_000_000.0 + index),
            adjustment_factor=1.0,
            suspended=False,
            benchmark_close=100.0 + index * 0.08,
            industry_close=100.0 + index * 0.09,
        )
        for index in range(252)
    )
    cutoff = datetime(2026, 8, 31, 15, tzinfo=UTC)
    return TechnicalAnalysisInput(
        instrument_id=InstrumentId(600519),
        instrument_name="贵州茅台",
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshot_ids=("market:sha256:performance",),
        spec=TechnicalAnalysisSpec(
            spec_id="performance-technical",
            spec_version="1",
            algorithm_version="technical-analysis.v1",
            timeframes=(TechnicalTimeframe.DAILY,),
        ),
        bars=bars,
        selection_run_id="selection-run:sha256:performance",
    )


class _ComparisonSource:
    def __init__(self, source: PortfolioComparisonSource) -> None:
        self._source = source

    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        del request
        return self._source


def _valuation(kind: str) -> PortfolioValuationInput:
    return PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of="2026-08-31",
        valuation_snapshot_id="valuation:performance",
        source_snapshot_ids=("market:sha256:performance",),
        currency="CNY",
        cash=Decimal("10000"),
        total_value=Decimal("100000"),
        positions=(
            PortfolioHoldingInput(
                instrument_id=600519,
                quantity=Decimal("100"),
                last_price=Decimal("600"),
                market_value=Decimal("60000"),
                industry="consumer",
            ),
            PortfolioHoldingInput(
                instrument_id=510300,
                quantity=Decimal("75"),
                last_price=Decimal("400"),
                market_value=Decimal("30000"),
                industry="fund",
            ),
        ),
        valuation_complete=True,
    )


def _comparison_operation() -> tuple[
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
]:
    source = PortfolioComparisonSource(
        model=_valuation("model"),
        paper=_valuation("paper"),
        manual=_valuation("manual"),
    )
    cutoff = datetime(2026, 8, 31, 15, tzinfo=UTC)
    request = PortfolioComparisonRequest(
        strategy_id="strategy-performance",
        model_portfolio_id="model-main",
        paper_account_id="paper-main",
        manual_account_id="manual-main",
        paper_session_id="paper-session-performance",
        as_of="2026-08-31",
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshot_ids=("market:sha256:performance",),
        valuation_snapshot_id="valuation:performance",
    )
    return GetPortfolioComparisonQuery(source=_ComparisonSource(source)), request


__all__ = ["default_workstation_performance_cases"]
