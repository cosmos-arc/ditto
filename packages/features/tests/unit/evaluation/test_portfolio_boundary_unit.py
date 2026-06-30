"""Comprehensive boundary tests for evaluation/metrics/portfolio.py.

Tests quantile_returns, long_short_returns, turnover, net_returns, and
turnover_adjusted_ir with edge cases not covered by test_metrics_unit.py.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_features.evaluation.metrics.portfolio import (
    long_short_returns,
    net_returns,
    quantile_returns,
    turnover,
    turnover_adjusted_ir,
)
from ditto_features.evaluation.report import LongShortResult

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_factor_return(
    n_dates: int = 20,
    n_entities: int = 50,
    *,
    seed: int = 42,
    ic_strength: float = 0.3,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create synthetic factor + return DataFrames."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(n_entities))

    rows_f: list[dict[str, object]] = []
    rows_r: list[dict[str, object]] = []

    for d in dates:
        signal = rng.standard_normal(n_entities)
        noise_f = rng.standard_normal(n_entities) * math.sqrt(1 - ic_strength)
        noise_r = rng.standard_normal(n_entities) * math.sqrt(1 - ic_strength)
        factor_vals = ic_strength * signal + noise_f
        return_vals = ic_strength * signal + noise_r

        for i, eid in enumerate(entities):
            rows_f.append(
                {"trade_date": d, "instrument_id": eid, "value": float(factor_vals[i])}
            )
            rows_r.append(
                {
                    "trade_date": d,
                    "instrument_id": eid,
                    "forward_return": float(return_vals[i]),
                }
            )

    return pl.DataFrame(rows_f), pl.DataFrame(rows_r)


# ---------------------------------------------------------------------------
# quantile_returns boundary
# ---------------------------------------------------------------------------


class TestQuantileReturnsBoundary:
    """Boundary tests for quantile_returns."""

    def test_two_quantiles(self) -> None:
        """n_quantiles=2 produces exactly 2 groups per date."""
        factor_df, return_df = _make_factor_return(n_dates=5, n_entities=30)
        result = quantile_returns(factor_df, return_df, n_quantiles=2)
        quantiles = result["quantile"].unique().sort().to_list()
        assert quantiles == [1, 2]
        assert result.height == 5 * 2

    def test_ten_quantiles(self) -> None:
        """n_quantiles=10 produces exactly 10 groups per date."""
        factor_df, return_df = _make_factor_return(n_dates=3, n_entities=100)
        result = quantile_returns(factor_df, return_df, n_quantiles=10)
        quantiles = result["quantile"].unique().sort().to_list()
        assert len(quantiles) == 10

    def test_single_date(self) -> None:
        """Single date produces one set of quantile groups."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 20,
                "instrument_id": list(range(20)),
                "value": [float(i) for i in range(20)],
            }
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 20,
                "instrument_id": list(range(20)),
                "forward_return": [float(i) * 0.01 for i in range(20)],
            }
        )
        result = quantile_returns(factor_df, return_df, n_quantiles=5)
        assert result.height == 5
        # Higher factor values should have higher returns (monotonic)
        mean_rets = result.sort("quantile")["mean_return"].to_list()
        assert mean_rets == sorted(mean_rets)

    def test_custom_column_names(self) -> None:
        """Custom column names are respected."""
        factor_df = pl.DataFrame(
            {
                "dt": [date(2024, 1, 1)] * 20,
                "asset": list(range(20)),
                "score": [float(i) for i in range(20)],
            }
        )
        return_df = pl.DataFrame(
            {
                "dt": [date(2024, 1, 1)] * 20,
                "asset": list(range(20)),
                "ret": [float(i) * 0.01 for i in range(20)],
            }
        )
        result = quantile_returns(
            factor_df,
            return_df,
            n_quantiles=5,
            factor_col="score",
            return_col="ret",
            date_col="dt",
            entity_col="asset",
        )
        assert result.height == 5


# ---------------------------------------------------------------------------
# long_short_returns boundary
# ---------------------------------------------------------------------------


class TestLongShortReturnsBoundary:
    """Boundary tests for long_short_returns."""

    def _make_q_ret(
        self,
        n_dates: int = 50,
        n_quantiles: int = 5,
        *,
        seed: int = 42,
        spread: float = 0.01,
    ) -> pl.DataFrame:
        """Create quantile return data with known spread."""
        rng = np.random.default_rng(seed)
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_dates)]
        rows = []
        for d in dates:
            for q in range(1, n_quantiles + 1):
                base = spread * q / n_quantiles
                noise = rng.normal(0, 0.005)
                rows.append(
                    {"trade_date": d, "quantile": q, "mean_return": base + noise}
                )
        return pl.DataFrame(rows)

    def test_positive_spread_produces_positive_return(self) -> None:
        """Positive LS spread produces positive annual return."""
        q_ret = self._make_q_ret(spread=0.02)
        result = long_short_returns(q_ret)
        assert result.annual_return > 0

    def test_single_date(self) -> None:
        """Single date produces valid result."""
        q_ret = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "quantile": [1, 2, 3, 4, 5],
                "mean_return": [-0.02, -0.01, 0.0, 0.01, 0.02],
            }
        )
        result = long_short_returns(q_ret)
        assert isinstance(result, LongShortResult)
        # LS = top - bottom = 0.02 - (-0.02) = 0.04
        assert result.annual_return > 0

    def test_zero_spread(self) -> None:
        """Equal top and bottom returns produce near-zero LS return."""
        q_ret = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "quantile": [1, 2, 3, 4, 5],
                "mean_return": [0.01, 0.01, 0.01, 0.01, 0.01],
            }
        )
        result = long_short_returns(q_ret)
        assert result.annual_return == pytest.approx(0.0)

    def test_risk_free_rate_reduces_sharpe(self) -> None:
        """Higher risk-free rate reduces portfolio IR."""
        q_ret = self._make_q_ret(n_dates=100)
        result_0 = long_short_returns(q_ret, risk_free_rate=0.0)
        result_5 = long_short_returns(q_ret, risk_free_rate=0.05)
        if result_0.annual_volatility > 0:
            assert result_5.portfolio_ir <= result_0.portfolio_ir

    def test_all_same_quantile_returns_empty(self) -> None:
        """When top or bottom quantile is missing, returns empty result."""
        # Only quantile 1 and 2 exist, but we ask for 5 and 1
        q_ret = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 2,
                "quantile": [1, 2],
                "mean_return": [0.01, 0.02],
            }
        )
        result = long_short_returns(q_ret, top_quantile=5, bottom_quantile=1)
        assert result.annual_return == 0.0
        assert result.annual_volatility == 0.0


# ---------------------------------------------------------------------------
# turnover boundary
# ---------------------------------------------------------------------------


class TestTurnoverBoundary:
    """Boundary tests for turnover."""

    def test_single_entity(self) -> None:
        """Single entity turnover computation."""
        current = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)],
                "instrument_id": [1],
                "weight": [1.0],
            }
        )
        previous = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)],
                "instrument_id": [1],
                "weight": [0.5],
            }
        )
        result = turnover(current, previous)
        # diff = 1.0 - 0.5 = 0.5; buys = 0.5, sells = 0
        # two_way = 0.5 * 0.5 = 0.25
        # one_way = min(0.5, 0) = 0
        assert result["turnover_two_way"][0] == pytest.approx(0.5 * 0.5)
        assert result["turnover_one_way"][0] == pytest.approx(0.0)

    def test_multiple_dates(self) -> None:
        """Turnover computed independently per date."""
        current = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "instrument_id": [1, 1],
                "weight": [0.8, 0.3],
            }
        )
        previous = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "instrument_id": [1, 1],
                "weight": [0.2, 0.7],
            }
        )
        result = turnover(current, previous)
        assert result.height == 2
        assert result["turnover_two_way"][0] == pytest.approx(0.5 * 0.6)
        assert result["turnover_two_way"][1] == pytest.approx(0.5 * 0.4)

    def test_complete_reversal(self) -> None:
        """Complete weight reversal: w_t=1, w_t-1=0 for all entities."""
        current = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 2,
                "instrument_id": [1, 2],
                "weight": [1.0, 0.0],
            }
        )
        previous = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 2,
                "instrument_id": [1, 2],
                "weight": [0.0, 1.0],
            }
        )
        result = turnover(current, previous)
        # Two-way: 0.5 * (|1-0| + |0-1|) = 0.5 * 2 = 1.0
        assert result["turnover_two_way"][0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# net_returns boundary
# ---------------------------------------------------------------------------


class TestNetReturnsBoundary:
    """Boundary tests for net_returns."""

    def test_zero_gross_return(self) -> None:
        """Zero gross return with any cost is negative."""
        result = net_returns(0.0, 1.0, cost_bps=20.0)
        assert result < 0

    def test_zero_cost(self) -> None:
        """Zero cost returns gross unchanged."""
        assert net_returns(0.10, 1.0, cost_bps=0.0) == pytest.approx(0.10)

    def test_very_high_turnover(self) -> None:
        """Very high turnover significantly reduces returns."""
        result = net_returns(0.05, 10.0, cost_bps=50.0)
        expected = 0.05 - 10.0 * 50.0 / 10000.0
        assert result == pytest.approx(expected)

    def test_negative_gross_return(self) -> None:
        """Negative gross return with costs makes it more negative."""
        result = net_returns(-0.05, 0.5, cost_bps=20.0)
        assert result < -0.05


# ---------------------------------------------------------------------------
# turnover_adjusted_ir boundary
# ---------------------------------------------------------------------------


class TestTurnoverAdjustedIRBoundary:
    """Boundary tests for turnover_adjusted_ir."""

    def test_negative_autocorr(self) -> None:
        """Negative autocorrelation changes the IR value."""
        ir_zero = turnover_adjusted_ir(0.05, 0.0)
        ir_neg = turnover_adjusted_ir(0.05, -0.5)
        assert ir_neg != ir_zero
        assert math.isfinite(ir_neg)

    def test_autocorr_exactly_one(self) -> None:
        """Autocorrelation of 1.0 may cause denominator issues."""
        result = turnover_adjusted_ir(0.05, 1.0)
        assert math.isfinite(result)

    def test_autocorr_exactly_negative_one(self) -> None:
        """Autocorrelation of -1.0 may cause denominator issues."""
        result = turnover_adjusted_ir(0.05, -1.0)
        assert math.isfinite(result)

    def test_very_small_rebalance_freq(self) -> None:
        """Very small rebalance frequency (1 day)."""
        result = turnover_adjusted_ir(0.05, 0.0, rebalance_freq=1)
        assert math.isfinite(result)
        # With freq=1, BR = total_periods, so IR should be large
        assert result > 0

    def test_large_rebalance_freq(self) -> None:
        """Large rebalance frequency."""
        result = turnover_adjusted_ir(0.05, 0.0, rebalance_freq=244)
        assert result > 0
        # With freq=244, BR = 1, so IR = IC * 1
        assert result == pytest.approx(0.05, abs=1e-6)

    @pytest.mark.parametrize("rho", [-0.9, -0.5, 0.0, 0.5, 0.9])
    def test_various_autocorrelations_finite(self, rho: float) -> None:
        """Various autocorrelations produce finite results."""
        result = turnover_adjusted_ir(0.05, rho)
        assert math.isfinite(result)
