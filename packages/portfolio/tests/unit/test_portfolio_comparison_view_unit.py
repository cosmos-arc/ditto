"""Deterministic MODEL/PAPER/MANUAL normalization and drift tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from ditto_portfolio.portfolio_comparison import (
    PortfolioAttribution,
    PortfolioComparisonError,
    PortfolioHoldingInput,
    PortfolioValuationInput,
    compare_portfolio_pair,
    constrained_target_weights,
    normalize_portfolio,
)


def _portfolio(
    kind: str,
    *,
    as_of: str = "2026-08-31",
    valuation_snapshot_id: str = "valuation:snapshot-1",
    first_value: str = "60000",
    second_value: str = "30000",
) -> PortfolioValuationInput:
    return PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of=as_of,
        valuation_snapshot_id=valuation_snapshot_id,
        source_snapshot_ids=("snapshot:stock", "snapshot:etf"),
        currency="CNY",
        cash=Decimal("10000"),
        total_value=Decimal("100000"),
        positions=(
            PortfolioHoldingInput(
                instrument_id=600519,
                quantity=Decimal("100"),
                last_price=Decimal("600"),
                market_value=Decimal(first_value),
                average_cost_value=Decimal("55000"),
                unrealized_pnl=Decimal("5000"),
                industry="consumer",
            ),
            PortfolioHoldingInput(
                instrument_id=510300,
                quantity=Decimal("75"),
                last_price=Decimal("400"),
                market_value=Decimal(second_value),
                average_cost_value=Decimal("29000"),
                unrealized_pnl=Decimal("1000"),
                industry="fund",
            ),
        ),
        valuation_complete=True,
    )


def test_normalization_preserves_cash_and_money_weight_identity() -> None:
    normalized = normalize_portfolio(_portfolio("model"))

    assert normalized.cash_weight == Decimal("0.10000000")
    assert tuple(position.weight for position in normalized.positions) == (
        Decimal("0.30000000"),
        Decimal("0.60000000"),
    )
    assert normalized.invested_weight + normalized.cash_weight == Decimal("1.00000000")


def test_pairwise_drift_keeps_paper_and_manual_attribution_semantics_distinct() -> None:
    model = normalize_portfolio(_portfolio("model"))
    paper = normalize_portfolio(
        _portfolio("paper", first_value="55000", second_value="35000")
    )
    manual = normalize_portfolio(
        _portfolio("manual", first_value="50000", second_value="40000")
    )

    paper_drift = compare_portfolio_pair(
        model,
        paper,
        attribution=PortfolioAttribution(
            unfilled_bps=Decimal("250"),
            slippage_amount=Decimal("12.50"),
            fee_amount=Decimal("5.00"),
            risk_blocked_bps=Decimal("100"),
        ),
    )
    manual_drift = compare_portfolio_pair(
        model,
        manual,
        attribution=PortfolioAttribution(user_choice_bps=Decimal("1500")),
    )

    assert paper_drift.comparison_kind == "model_vs_paper"
    assert paper_drift.attribution.unfilled_bps == Decimal("250")
    assert paper_drift.attribution.user_choice_bps == Decimal("0")
    assert manual_drift.comparison_kind == "model_vs_manual"
    assert manual_drift.attribution.user_choice_bps == Decimal("1500")
    assert manual_drift.attribution.unfilled_bps == Decimal("0")


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("as_of", "2026-08-30", "as_of"),
        ("valuation_snapshot_id", "valuation:snapshot-2", "valuation snapshot"),
        ("source_snapshot_ids", ("snapshot:future",), "source snapshot"),
    ],
)
def test_pairwise_comparison_fails_closed_on_identity_drift(
    field: str,
    replacement: object,
    message: str,
) -> None:
    from dataclasses import replace

    model = normalize_portfolio(_portfolio("model"))
    observed_input = replace(_portfolio("paper"), **{field: replacement})

    with pytest.raises(PortfolioComparisonError, match=message):
        compare_portfolio_pair(model, normalize_portfolio(observed_input))


def test_future_sentinel_is_not_admitted_by_a_matching_as_of_label() -> None:
    model = normalize_portfolio(_portfolio("model"))
    future = normalize_portfolio(
        PortfolioValuationInput(
            **{
                **_portfolio("paper").__dict__,
                "source_snapshot_ids": ("snapshot:stock:future-2026-09-01",),
            }
        )
    )

    with pytest.raises(PortfolioComparisonError, match="source snapshot"):
        compare_portfolio_pair(model, future)


def test_constraint_target_is_deterministic_capped_and_cash_preserving() -> None:
    target = constrained_target_weights(
        {600519: Decimal("0.60"), 510300: Decimal("0.30"), 159915: Decimal("0.05")},
        excluded_instrument_ids=frozenset({159915}),
        max_position_weight=Decimal("0.50"),
        cash_reserve_weight=Decimal("0.10"),
    )

    assert target == {
        510300: Decimal("0.40000000"),
        600519: Decimal("0.50000000"),
    }
    assert sum(target.values()) == Decimal("0.90000000")


@pytest.mark.parametrize(
    ("baseline_weights", "excluded_instrument_ids", "message"),
    [
        (
            {600519: Decimal("-0.10"), 510300: Decimal("0.80")},
            frozenset(),
            "baseline weights",
        ),
        (
            {600519: Decimal("0.60"), 510300: Decimal("0.30")},
            frozenset({-1}),
            "excluded instrument",
        ),
    ],
)
def test_constraint_target_rejects_invalid_baseline_or_exclusion_identity(
    baseline_weights: dict[int, Decimal],
    excluded_instrument_ids: frozenset[int],
    message: str,
) -> None:
    with pytest.raises(PortfolioComparisonError, match=message):
        constrained_target_weights(
            baseline_weights,
            excluded_instrument_ids=excluded_instrument_ids,
            max_position_weight=Decimal("0.80"),
            cash_reserve_weight=Decimal("0.20"),
        )
