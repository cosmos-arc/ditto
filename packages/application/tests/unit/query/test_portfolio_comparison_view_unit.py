"""Application aggregation tests for exact three-portfolio comparisons."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
    PortfolioComparisonSource,
)
from ditto_portfolio.portfolio_comparison import (
    PortfolioAttribution,
    PortfolioHoldingInput,
    PortfolioValuationInput,
)


def _valuation(kind: str, *, as_of: str = "2026-08-31") -> PortfolioValuationInput:
    values = {
        "model": ("60000", "30000"),
        "paper": ("55000", "35000"),
        "manual": ("50000", "40000"),
    }[kind]
    return PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of=as_of,
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
                market_value=Decimal(values[0]),
                industry="consumer",
            ),
            PortfolioHoldingInput(
                instrument_id=510300,
                quantity=Decimal("75"),
                last_price=Decimal("400"),
                market_value=Decimal(values[1]),
                industry="fund",
            ),
        ),
        valuation_complete=True,
    )


class _Source:
    def __init__(self, source: PortfolioComparisonSource) -> None:
        self.source = source
        self.reads = 0
        self.writes = 0

    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        self.reads += 1
        return self.source


def _request() -> PortfolioComparisonRequest:
    return PortfolioComparisonRequest(
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
    )


def test_query_aggregates_three_valuations_and_semantic_drift() -> None:
    source = _Source(
        PortfolioComparisonSource(
            model=_valuation("model"),
            paper=_valuation("paper"),
            manual=_valuation("manual"),
            paper_attribution=PortfolioAttribution(
                unfilled_bps=Decimal("250"),
                slippage_amount=Decimal("12.50"),
                fee_amount=Decimal("5"),
                risk_blocked_bps=Decimal("100"),
            ),
            manual_attribution=PortfolioAttribution(user_choice_bps=Decimal("1000")),
        )
    )

    view = GetPortfolioComparisonQuery(source=source).get(_request())

    assert view.as_of == "2026-08-31"
    assert view.model.portfolio_kind == "model"
    assert view.paper.portfolio_kind == "paper"
    assert view.manual.portfolio_kind == "manual"
    assert view.model_vs_paper.attribution.unfilled_bps == Decimal("250")
    assert view.model_vs_manual.attribution.user_choice_bps == Decimal("1000")
    assert view.paper_vs_manual.comparison_kind == "paper_vs_manual"
    assert source.reads == 1
    assert source.writes == 0


def test_query_fails_closed_when_source_leg_or_request_identity_drifts() -> None:
    source = _Source(
        PortfolioComparisonSource(
            model=_valuation("model"),
            paper=_valuation("paper", as_of="2026-08-30"),
            manual=_valuation("manual"),
        )
    )

    with pytest.raises(AppQueryError) as error:
        GetPortfolioComparisonQuery(source=source).get(_request())

    assert error.value.details["code"] == "PORTFOLIO_COMPARISON_IDENTITY_MISMATCH"
    assert "as_of" in str(error.value)


def test_query_rejects_future_sentinel_snapshot_even_if_source_echoes_request() -> None:
    request = PortfolioComparisonRequest(
        **{
            **_request().__dict__,
            "source_snapshot_ids": ("snapshot:future:2026-09-01",),
        }
    )
    source = _Source(
        PortfolioComparisonSource(
            model=_valuation("model"),
            paper=_valuation("paper"),
            manual=_valuation("manual"),
        )
    )

    with pytest.raises(AppQueryError) as error:
        GetPortfolioComparisonQuery(source=source).get(request)

    assert error.value.details["code"] == "PORTFOLIO_COMPARISON_IDENTITY_MISMATCH"
