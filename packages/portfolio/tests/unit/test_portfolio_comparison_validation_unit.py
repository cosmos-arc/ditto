"""Validation and semantic-attribution tests for portfolio comparisons."""

from __future__ import annotations

from dataclasses import replace
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


def _holding(**changes: object) -> PortfolioHoldingInput:
    holding = PortfolioHoldingInput(
        instrument_id=600519,
        quantity=Decimal("10"),
        last_price=Decimal("8"),
        market_value=Decimal("80"),
    )
    return replace(holding, **changes)


def _portfolio(kind: str = "model", **changes: object) -> PortfolioValuationInput:
    value = PortfolioValuationInput(
        portfolio_id=f"{kind}-main",
        portfolio_kind=kind,
        as_of="2026-09-04",
        valuation_snapshot_id="valuation:2026-09-04",
        source_snapshot_ids=("market:2026-09-04",),
        currency="CNY",
        cash=Decimal("20"),
        total_value=Decimal("100"),
        positions=(_holding(),),
        valuation_complete=True,
    )
    return replace(value, **changes)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (_portfolio(portfolio_id=" "), "portfolio_id"),
        (_portfolio(portfolio_kind="unknown"), "portfolio_kind"),
        (_portfolio(as_of="not-a-date"), "as_of"),
        (_portfolio(valuation_snapshot_id=""), "valuation_snapshot_id"),
        (_portfolio(source_snapshot_ids=()), "source snapshot IDs"),
        (
            _portfolio(source_snapshot_ids=("market", "market")),
            "source snapshot IDs",
        ),
        (_portfolio(source_snapshot_ids=(" ",)), "source_snapshot_id"),
        (_portfolio(currency="USD"), "requires CNY"),
        (_portfolio(valuation_complete=False), "incomplete"),
        (_portfolio(pending_event_count=-1), "pending_event_count"),
    ],
)
def test_normalization_requires_exact_complete_portfolio_identity(
    value: PortfolioValuationInput,
    message: str,
) -> None:
    with pytest.raises(PortfolioComparisonError, match=message):
        normalize_portfolio(value)


@pytest.mark.parametrize(
    ("positions", "message"),
    [
        ((_holding(instrument_id=0),), "positive and unique"),
        ((_holding(), _holding()), "positive and unique"),
        ((_holding(quantity=Decimal("NaN")),), "quantity must be finite"),
        ((_holding(market_value=Decimal("-1")),), "cannot be negative"),
        (
            (_holding(quantity=Decimal("1"), last_price=Decimal("0")),),
            "positive last_price",
        ),
    ],
)
def test_normalization_rejects_invalid_position_evidence(
    positions: tuple[PortfolioHoldingInput, ...],
    message: str,
) -> None:
    with pytest.raises(PortfolioComparisonError, match=message):
        normalize_portfolio(_portfolio(positions=positions))


def test_normalization_requires_positive_balanced_value_and_weights() -> None:
    with pytest.raises(PortfolioComparisonError, match="total_value"):
        normalize_portfolio(_portfolio(total_value=Decimal("0")))
    with pytest.raises(PortfolioComparisonError, match="cash cannot be negative"):
        normalize_portfolio(_portfolio(cash=Decimal("-1")))
    with pytest.raises(PortfolioComparisonError, match="does not equal"):
        normalize_portfolio(_portfolio(total_value=Decimal("101")))
    with pytest.raises(PortfolioComparisonError, match="weights do not sum"):
        normalize_portfolio(
            _portfolio(
                total_value=Decimal("3.00"),
                cash=Decimal("1.00"),
                positions=(
                    _holding(
                        quantity=Decimal("1"),
                        last_price=Decimal("1.99"),
                        market_value=Decimal("1.99"),
                    ),
                ),
            )
        )


def test_comparison_rejects_currency_drift() -> None:
    model = normalize_portfolio(_portfolio("model"))
    paper = replace(normalize_portfolio(_portfolio("paper")), currency="USD")
    with pytest.raises(PortfolioComparisonError, match="currency mismatch"):
        compare_portfolio_pair(model, paper)


def test_attribution_cannot_mislabel_manual_or_paper_drift() -> None:
    model = normalize_portfolio(_portfolio("model"))
    paper = normalize_portfolio(_portfolio("paper"))
    manual = normalize_portfolio(_portfolio("manual"))

    with pytest.raises(PortfolioComparisonError, match="cannot be negative"):
        compare_portfolio_pair(
            model,
            paper,
            attribution=PortfolioAttribution(fee_amount=Decimal("-0.01")),
        )
    with pytest.raises(PortfolioComparisonError, match="execution failure"):
        compare_portfolio_pair(
            model,
            manual,
            attribution=PortfolioAttribution(unfilled_bps=Decimal("1")),
        )
    with pytest.raises(PortfolioComparisonError, match="user choice"):
        compare_portfolio_pair(
            model,
            paper,
            attribution=PortfolioAttribution(user_choice_bps=Decimal("1")),
        )


def test_scenario_constraints_fail_closed_when_target_cannot_be_funded() -> None:
    weights = {600519: Decimal("0.6"), 510300: Decimal("0.4")}
    with pytest.raises(PortfolioComparisonError, match="constraints are invalid"):
        constrained_target_weights(
            weights,
            max_position_weight=Decimal("0"),
            cash_reserve_weight=Decimal("0.1"),
        )
    with pytest.raises(PortfolioComparisonError, match="exclude every"):
        constrained_target_weights(
            weights,
            excluded_instrument_ids=frozenset(weights),
            max_position_weight=Decimal("1"),
            cash_reserve_weight=Decimal("0.1"),
        )
    with pytest.raises(PortfolioComparisonError, match="cannot satisfy"):
        constrained_target_weights(
            weights,
            max_position_weight=Decimal("0.4"),
            cash_reserve_weight=Decimal("0.1"),
        )
