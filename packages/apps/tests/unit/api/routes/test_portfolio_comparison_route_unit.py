"""CMP-05 comparison and scenario HTTP contract tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import patch

from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
    PortfolioComparisonSource,
)
from ditto_application.queries.portfolio_scenario import PreviewPortfolioScenarioQuery
from ditto_apps.api.routes.portfolio_comparison import (
    get_portfolio_comparison,
    preview_portfolio_scenario,
)
from ditto_apps.models.portfolio_comparison import (
    PortfolioComparisonQueryParams,
    PortfolioScenarioBody,
)
from ditto_apps.openapi_contract import create_openapi_app
from ditto_portfolio.portfolio_comparison import (
    PortfolioHoldingInput,
    PortfolioValuationInput,
)

NOW = datetime(2026, 8, 31, 15, tzinfo=UTC)


def _valuation(kind: str) -> PortfolioValuationInput:
    return PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of="2026-08-31",
        valuation_snapshot_id="portfolio-valuation:sha256:abc",
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


class _Source:
    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        return PortfolioComparisonSource(
            model=_valuation("model"),
            paper=_valuation("paper"),
            manual=_valuation("manual"),
        )


async def _inline(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


def _original(function: Callable[..., object]) -> Callable[..., object]:
    return cast(Callable[..., object], function.__dict__["__dishka_orig_func__"])


def test_routes_return_comparison_and_read_only_scenario() -> None:
    comparison = GetPortfolioComparisonQuery(source=_Source())
    scenario = PreviewPortfolioScenarioQuery(comparison=comparison)
    with patch(
        "ditto_apps.api.routes.portfolio_comparison.asyncio.to_thread",
        side_effect=_inline,
    ):
        compared = asyncio.run(
            _original(get_portfolio_comparison)(
                params=PortfolioComparisonQueryParams(
                    strategy_id="strategy-1",
                    model_portfolio_id="model-main",
                    paper_account_id="paper-main",
                    manual_account_id="manual-main",
                    paper_session_id="session-1",
                    as_of=date(2026, 8, 31),
                    knowledge_cutoff=NOW,
                    publication_cutoff=NOW,
                    source_snapshot_ids=("snapshot:stock",),
                ),
                query=comparison,
            )
        )
        previewed = asyncio.run(
            _original(preview_portfolio_scenario)(
                body=PortfolioScenarioBody(
                    strategy_id="strategy-1",
                    model_portfolio_id="model-main",
                    paper_account_id="paper-main",
                    manual_account_id="manual-main",
                    paper_session_id="session-1",
                    as_of=date(2026, 8, 31),
                    knowledge_cutoff=NOW,
                    publication_cutoff=NOW,
                    source_snapshot_ids=("snapshot:stock",),
                    baseline_kind="model",
                    excluded_instrument_ids=(),
                    max_position_weight=Decimal("0.50"),
                    cash_reserve_weight=Decimal("0.10"),
                    market_shock=-0.10,
                    industry_shocks={"consumer": -0.20},
                ),
                query=scenario,
            )
        )

    assert compared.data.model.portfolio_kind == "model"
    assert compared.data.model_vs_manual.attribution.user_choice_bps == Decimal("0")
    assert previewed.data.proposed_weights == {
        510300: Decimal("0.40000000"),
        600519: Decimal("0.50000000"),
    }
    assert previewed.data.risk.after.stressed_return == -0.19


def test_openapi_registers_stable_portfolio_comparison_operations() -> None:
    schema = create_openapi_app().openapi()
    comparison = schema["paths"]["/api/v1/portfolio/comparison"]["get"]

    assert comparison["operationId"] == "portfolio_get_comparison"
    assert "requestBody" not in comparison
    source_snapshots = next(
        parameter
        for parameter in comparison["parameters"]
        if parameter["name"] == "source_snapshot_ids"
    )
    assert source_snapshots["in"] == "query"
    assert source_snapshots["required"] is True
    assert source_snapshots["schema"]["type"] == "array"
    assert (
        schema["paths"]["/api/v1/portfolio/scenario-previews"]["post"]["operationId"]
        == "portfolio_preview_scenario"
    )


def test_scenario_body_accepts_json_array_fields() -> None:
    body = PortfolioScenarioBody.model_validate(
        {
            "strategy_id": "strategy-1",
            "model_portfolio_id": "model-main",
            "paper_account_id": "paper-main",
            "manual_account_id": "manual-main",
            "paper_session_id": "session-1",
            "as_of": "2026-08-31",
            "knowledge_cutoff": NOW.isoformat(),
            "publication_cutoff": NOW.isoformat(),
            "source_snapshot_ids": ["snapshot:stock"],
            "baseline_kind": "model",
            "excluded_instrument_ids": [600519],
            "max_position_weight": "0.50",
            "cash_reserve_weight": "0.10",
        }
    )

    assert body.source_snapshot_ids == ("snapshot:stock",)
    assert body.excluded_instrument_ids == (600519,)
