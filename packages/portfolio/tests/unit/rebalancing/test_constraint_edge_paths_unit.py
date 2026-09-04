"""Fail-safe defaults and identifier handling for launch constraints."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_portfolio.rebalancing.constraints import (
    IndustryMaxWeightConstraint,
    LiquidityConstraint,
    MaxTurnoverConstraint,
    TradabilityConstraint,
)


def _frame(**columns: list[object]) -> pl.DataFrame:
    values: dict[str, list[object]] = {
        "instrument_id": [1, 2],
        "weight": [0.6, 0.4],
    }
    values.update(columns)
    return pl.DataFrame(values, strict=False)


def test_optional_market_columns_leave_weights_unchanged_when_absent() -> None:
    frame = _frame()
    weights = {1: 0.6, 2: 0.4}

    assert (
        IndustryMaxWeightConstraint().check(weights, frame).adjusted_weights == weights
    )
    assert LiquidityConstraint().check(weights, frame).adjusted_weights == weights
    assert TradabilityConstraint().check(weights, frame).adjusted_weights == weights


def test_liquidity_rejects_unparseable_scalar_evidence() -> None:
    weights = {1: 0.6, 2: 0.4}
    object_frame = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "weight": [0.6, 0.4],
            "avg_daily_turnover": pl.Series(
                [{"invalid": True}, 10.0],
                dtype=pl.Object,
            ),
        }
    )
    string_frame = _frame(avg_daily_turnover=["not-a-number", "10"])

    object_result = LiquidityConstraint(min_liquidity=5.0).check(weights, object_frame)
    string_result = LiquidityConstraint(min_liquidity=5.0).check(weights, string_frame)
    assert object_result.adjusted_weights[1] == 0.0
    assert object_result.adjusted_weights[2] == pytest.approx(0.4)
    assert string_result.adjusted_weights[1] == 0.0
    assert string_result.adjusted_weights[2] == pytest.approx(0.4)


def test_tradability_parses_missing_and_canonical_string_flags() -> None:
    frame = _frame(is_st=[None, " yes "])
    result = TradabilityConstraint().check({1: 0.6, 2: 0.4}, frame)

    assert result.adjusted_weights == {1: 0.6, 2: 0.0}
    assert result.reason_codes == ("st_exclusion: 2 marked ST",)


def test_turnover_noop_and_previous_weight_identifier_fallbacks() -> None:
    frame = _frame(previous_weight=["0.6", "invalid"])
    weights = {1: 0.6, 2: 0.4}

    no_previous = MaxTurnoverConstraint(max_turnover=0.0).check(weights, _frame())
    assert no_previous.adjusted_weights == weights
    assert no_previous.reason_codes == ()

    unchanged = MaxTurnoverConstraint(max_turnover=1.0).check(weights, frame)
    assert unchanged.adjusted_weights == weights

    string_keyed = MaxTurnoverConstraint(
        max_turnover=0.0,
        previous_weights={"1": 0.2, "other": 0.1},
    ).check(weights, _frame())
    assert string_keyed.adjusted_weights == {1: 0.2, 2: 0.0}
    assert string_keyed.reason_codes
