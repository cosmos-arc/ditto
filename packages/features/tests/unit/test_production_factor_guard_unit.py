"""Production safety guard tests for factor expressions."""

from __future__ import annotations

import pytest
from ditto_features.factors.production_guard import (
    UnsafeProductionFactorExpressionError,
    validate_production_factor_expression,
)


def test_rejects_cross_section_wrapping_inline_time_series_expression() -> None:
    with pytest.raises(
        UnsafeProductionFactorExpressionError,
        match="nests cross-sectional and time-series operators",
    ):
        validate_production_factor_expression(
            "cs_rank(ts_mean(market.close, 20))",
        )


def test_allows_simple_cross_section_expression() -> None:
    validate_production_factor_expression("cs_zscore(roe)")


def test_time_series_intermediate_requires_materialization_marker() -> None:
    with pytest.raises(
        UnsafeProductionFactorExpressionError,
        match="ts_mean_close_20",
    ):
        validate_production_factor_expression("cs_rank(ts_mean_close_20)")

    validate_production_factor_expression(
        "cs_rank(ts_mean_close_20)",
        materialized_columns={"ts_mean_close_20"},
    )
