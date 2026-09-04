"""Read-only application portfolio scenario preview tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
    PortfolioComparisonSource,
)
from ditto_application.queries.portfolio_scenario import (
    PortfolioScenarioRequest,
    PreviewPortfolioScenarioQuery,
)
from ditto_portfolio.portfolio_comparison import (
    PortfolioHoldingInput,
    PortfolioValuationInput,
)


def _valuation(kind: str) -> PortfolioValuationInput:
    return PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of="2026-08-31",
        valuation_snapshot_id="valuation:snapshot-1",
        source_snapshot_ids=("snapshot:stock",),
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


class _ReadOnlySource:
    def __init__(self) -> None:
        self.reads = 0
        self.mutations = 0

    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        self.reads += 1
        return PortfolioComparisonSource(
            model=_valuation("model"),
            paper=_valuation("paper"),
            manual=_valuation("manual"),
        )

    def mutate(self) -> None:
        self.mutations += 1


def test_preview_computes_target_and_risk_without_account_or_target_writes() -> None:
    source = _ReadOnlySource()
    comparison = GetPortfolioComparisonQuery(source=source)
    query = PreviewPortfolioScenarioQuery(comparison=comparison)

    preview = query.preview(
        PortfolioScenarioRequest(
            comparison=PortfolioComparisonRequest(
                strategy_id="strategy-1",
                model_portfolio_id="model-main",
                paper_account_id="paper-main",
                manual_account_id="manual-main",
                paper_session_id="paper-session-1",
                as_of="2026-08-31",
                knowledge_cutoff=datetime(2026, 8, 31, 15, tzinfo=UTC),
                publication_cutoff=datetime(2026, 8, 31, 15, tzinfo=UTC),
                source_snapshot_ids=("snapshot:stock",),
                valuation_snapshot_id="valuation:snapshot-1",
            ),
            baseline_kind="model",
            excluded_instrument_ids=frozenset(),
            max_position_weight=Decimal("0.50"),
            cash_reserve_weight=Decimal("0.10"),
            market_shock=-0.10,
            industry_shocks={"consumer": -0.20},
        )
    )

    assert preview.proposed_weights == {
        510300: Decimal("0.40000000"),
        600519: Decimal("0.50000000"),
    }
    assert preview.risk.after.stressed_return == -0.19
    assert source.reads == 1
    assert source.mutations == 0
