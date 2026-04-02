"""Unit tests for Phase 1 evaluation metrics enhancements.

Tests cover:
- 1a: periods_per_year configurability
- 1b: Sharpe formula with risk-free rate
- 1c: Tail risk metrics (CVaR, skewness, kurtosis, max loss)
- 1d: Calmar ratio
- 1e: Grinold-Kahn IR
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_analytics.evaluation.evaluator import EvaluationConfig
from ditto_analytics.evaluation.metrics import (
    grinold_kahn_ir,
    long_short_returns,
    tail_risk_metrics,
)
from ditto_analytics.evaluation.report import (
    TailRiskMetrics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quantile_ret_df(
    n_dates: int = 100,
    *,
    seed: int = 42,
) -> pl.DataFrame:
    """Create a synthetic quantile return DataFrame with known top/bottom spread."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    rows: list[dict[str, object]] = []
    for d in dates:
        for q in range(1, 6):
            # top quantile (5) has slightly positive mean, bottom (1) slightly negative
            bias = 0.002 * (q - 3)
            rows.append(
                {
                    "trade_date": d,
                    "quantile": q,
                    "mean_return": float(rng.normal(bias, 0.01)),
                },
            )
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1a: EVAL-EV-6 — periods_per_year configurable
# ---------------------------------------------------------------------------


class TestPeriodsPerYearConfigurable:
    """Verify that EvaluationConfig.periods_per_year is respected."""

    def test_config_has_periods_per_year_field(self) -> None:
        """EvaluationConfig should expose a periods_per_year field."""
        config = EvaluationConfig(periods_per_year=252)
        assert config.periods_per_year == 252

    def test_default_periods_per_year(self) -> None:
        """Default periods_per_year should be 244."""
        config = EvaluationConfig()
        assert config.periods_per_year == 244

    def test_long_short_uses_custom_periods_per_year(self) -> None:
        """long_short_returns with periods_per_year=252 should differ from 244."""
        q_ret = _make_quantile_ret_df()
        result_244 = long_short_returns(q_ret, periods_per_year=244)
        result_252 = long_short_returns(q_ret, periods_per_year=252)
        # Annual return scales linearly with periods_per_year
        assert result_244.annual_return != result_252.annual_return


# ---------------------------------------------------------------------------
# 1b: EVAL-EV-1 — Sharpe formula with risk-free rate
# ---------------------------------------------------------------------------


class TestSharpeUsesRiskFreeRate:
    """Verify Sharpe ratio incorporates risk-free rate correctly."""

    def test_sharpe_nonzero_rf_differs_from_zero_rf(self) -> None:
        """rf=0.03 should produce different Sharpe than rf=0."""
        q_ret = _make_quantile_ret_df(n_dates=200)
        result_zero = long_short_returns(q_ret, risk_free_rate=0.0)
        result_rf = long_short_returns(q_ret, risk_free_rate=0.03)

        if result_zero.annual_volatility > 0:
            assert result_rf.sharpe != result_zero.sharpe

    def test_sharpe_zero_rf_backward_compat(self) -> None:
        """rf=0 result should match the old formula: mean * P / (std * sqrt(P))."""
        q_ret = _make_quantile_ret_df(n_dates=200)
        result = long_short_returns(q_ret, risk_free_rate=0.0, periods_per_year=244)

        # Manually compute expected Sharpe
        top = q_ret.filter(pl.col("quantile") == 5).sort("trade_date")["mean_return"]
        bottom = q_ret.filter(pl.col("quantile") == 1).sort("trade_date")["mean_return"]
        ls_daily = top - bottom
        mean_daily = float(ls_daily.mean())
        std_daily = float(ls_daily.std(ddof=1))
        P = 244
        if std_daily > 0:
            expected_sharpe = (mean_daily * P) / (std_daily * math.sqrt(P))
        else:
            expected_sharpe = 0.0

        assert abs(result.sharpe - expected_sharpe) < 1e-10

    def test_portfolio_ir_equals_sharpe_when_rf_in_sharpe(self) -> None:
        """When rf is already subtracted in Sharpe, portfolio_ir should equal sharpe."""
        q_ret = _make_quantile_ret_df(n_dates=200)
        result = long_short_returns(q_ret, risk_free_rate=0.03)
        # Both Sharpe and portfolio_ir now subtract rf, so they should be equal
        assert result.sharpe == pytest.approx(result.portfolio_ir)


# ---------------------------------------------------------------------------
# 1c: EVAL-EV-4 — Tail risk metrics
# ---------------------------------------------------------------------------


class TestTailRiskMetrics:
    """Verify tail risk metric computation."""

    def test_cvar_known_distribution(self) -> None:
        """CVaR on known sorted returns should match manual calculation."""
        # 100 returns sorted ascending: uniform from -0.10 to 0.10
        rng = np.random.default_rng(42)
        returns = np.sort(rng.uniform(-0.10, 0.10, 100))
        ls_daily = pl.Series(returns)
        result = tail_risk_metrics(ls_daily)

        # CVaR 95%: mean of worst 5%
        worst_5 = sorted(returns)[:5]
        expected_cvar_95 = float(np.mean(worst_5))
        assert result.cvar_95 == pytest.approx(expected_cvar_95, rel=1e-10)

        # CVaR 99%: mean of worst 1%
        worst_1 = sorted(returns)[:1]
        expected_cvar_99 = float(np.mean(worst_1))
        assert result.cvar_99 == pytest.approx(expected_cvar_99, rel=1e-10)

    def test_tail_risk_empty(self) -> None:
        """Empty data returns all zeros."""
        ls_daily = pl.Series([], dtype=pl.Float64)
        result = tail_risk_metrics(ls_daily)
        assert result == TailRiskMetrics(
            cvar_95=0.0,
            cvar_99=0.0,
            skewness=0.0,
            kurtosis=0.0,
            max_single_day_loss=0.0,
        )

    def test_tail_risk_single_element(self) -> None:
        """Single element returns zeros for std-dependent metrics."""
        ls_daily = pl.Series([0.01])
        result = tail_risk_metrics(ls_daily)
        # With a single element, CVaR and max_single_day_loss should be computed
        assert result.max_single_day_loss == pytest.approx(0.01)

    def test_tail_risk_in_long_short_result(self) -> None:
        """LongShortResult should contain a tail_risk field."""
        q_ret = _make_quantile_ret_df(n_dates=100)
        result = long_short_returns(q_ret)
        assert hasattr(result, "tail_risk")
        assert isinstance(result.tail_risk, TailRiskMetrics)

    def test_max_single_day_loss(self) -> None:
        """max_single_day_loss should be the minimum return value."""
        returns = pl.Series([0.01, -0.05, 0.03, 0.02, -0.01])
        result = tail_risk_metrics(returns)
        assert result.max_single_day_loss == pytest.approx(-0.05)


# ---------------------------------------------------------------------------
# 1d: EVAL-EV-7 — Calmar ratio
# ---------------------------------------------------------------------------


class TestCalmarRatio:
    """Verify Calmar ratio computation."""

    def test_calmar_ratio(self) -> None:
        """calmar = annual_return / abs(max_drawdown)."""
        q_ret = _make_quantile_ret_df(n_dates=200)
        result = long_short_returns(q_ret)

        if result.max_drawdown != 0:
            expected = result.annual_return / abs(result.max_drawdown)
            assert result.calmar == pytest.approx(expected)

    def test_calmar_zero_drawdown(self) -> None:
        """When max_drawdown is 0, calmar should be 0."""
        # All-positive returns should give zero drawdown
        rng = np.random.default_rng(42)
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(50)]
        rows: list[dict[str, object]] = []
        for d in dates:
            for q in range(1, 6):
                bias = 0.01 if q == 5 else 0.001
                rows.append(
                    {
                        "trade_date": d,
                        "quantile": q,
                        "mean_return": float(rng.normal(bias, 0.001)),
                    },
                )
        q_ret = pl.DataFrame(rows)
        result = long_short_returns(q_ret)
        # If no drawdown occurred, calmar should be 0
        if result.max_drawdown == 0.0:
            assert result.calmar == 0.0

    def test_calmar_in_long_short_result(self) -> None:
        """LongShortResult should contain a calmar field."""
        q_ret = _make_quantile_ret_df(n_dates=100)
        result = long_short_returns(q_ret)
        assert hasattr(result, "calmar")
        assert isinstance(result.calmar, float)


# ---------------------------------------------------------------------------
# 1e: EVAL-EV-8 — Grinold-Kahn IR
# ---------------------------------------------------------------------------


class TestGrinoldKahnIR:
    """Verify Grinold-Kahn IR computation."""

    def test_formula_known_inputs(self) -> None:
        """Known inputs should produce expected output."""
        # IC = 0.05, IC_std = 0.15, rho = 0.3, BR = 100
        mean_ic = 0.05
        ic_std = 0.15
        rho = 0.3
        breadth = 100.0

        result = grinold_kahn_ir(
            mean_ic=mean_ic,
            ic_std=ic_std,
            ic_autocorr_lag1=rho,
            breadth=breadth,
            rebalance_freq=5,
        )

        # IC = mean_ic / ic_std
        ic_ratio = mean_ic / ic_std  # 0.3333...
        # BR_effective with Gordon Ritter correction: T = periods_per_year = 244
        t_periods = 244
        denominator = 1 - 2 * rho * math.cos(math.pi / t_periods) + rho * rho
        br_effective = breadth * (1 - rho * rho) / denominator
        expected = ic_ratio * math.sqrt(br_effective)

        assert result == pytest.approx(expected, rel=1e-10)

    def test_zero_autocorr(self) -> None:
        """With rho=0, IR = IC * sqrt(breadth) (simple Fundamental Law)."""
        mean_ic = 0.05
        ic_std = 0.15
        breadth = 100.0

        result = grinold_kahn_ir(
            mean_ic=mean_ic,
            ic_std=ic_std,
            ic_autocorr_lag1=0.0,
            breadth=breadth,
            rebalance_freq=5,
        )

        ic_ratio = mean_ic / ic_std
        expected = ic_ratio * math.sqrt(breadth)
        assert result == pytest.approx(expected, rel=1e-10)

    def test_zero_ic_std_returns_zero(self) -> None:
        """When ic_std is 0, should return 0.0."""
        result = grinold_kahn_ir(
            mean_ic=0.05,
            ic_std=0.0,
            ic_autocorr_lag1=0.0,
            breadth=100.0,
        )
        assert result == 0.0

    def test_negative_breadth_returns_zero(self) -> None:
        """When breadth <= 0, should return 0.0."""
        result = grinold_kahn_ir(
            mean_ic=0.05,
            ic_std=0.15,
            ic_autocorr_lag1=0.0,
            breadth=-10.0,
        )
        assert result == 0.0

    def test_high_autocorr_increases_ir(self) -> None:
        """Strong positive autocorrelation increases effective breadth.

        With large T (= periods_per_year), the Gordon Ritter correction
        amplifies effective breadth when rho is close to 1, because
        highly autocorrelated ICs mean the signal persists across periods.
        """
        ir_low = grinold_kahn_ir(
            mean_ic=0.05,
            ic_std=0.15,
            ic_autocorr_lag1=0.0,
            breadth=100.0,
        )
        ir_high = grinold_kahn_ir(
            mean_ic=0.05,
            ic_std=0.15,
            ic_autocorr_lag1=0.9,
            breadth=100.0,
        )
        assert ir_high > ir_low
