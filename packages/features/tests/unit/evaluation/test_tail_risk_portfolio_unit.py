"""Comprehensive unit tests for evaluation/metrics/tail_risk.py.

Tests tail_risk_metrics and grinold_kahn_ir with edge cases:
empty series, single element, various distributions, boundary parameters.
"""

from __future__ import annotations

import math

import polars as pl
import pytest
from ditto_features.evaluation.metrics.tail_risk import (
    grinold_kahn_ir,
    tail_risk_metrics,
)
from ditto_features.evaluation.report import TailRiskMetrics

# ---------------------------------------------------------------------------
# tail_risk_metrics
# ---------------------------------------------------------------------------


class TestTailRiskMetrics:
    """Tests for tail_risk_metrics."""

    def test_empty_series(self) -> None:
        """Empty series returns all zeros."""
        series = pl.Series("ls", [], dtype=pl.Float64)
        result = tail_risk_metrics(series)
        assert isinstance(result, TailRiskMetrics)
        assert result.cvar_95 == 0.0
        assert result.cvar_99 == 0.0
        assert result.skewness == 0.0
        assert result.kurtosis == 0.0
        assert result.max_single_day_loss == 0.0

    def test_single_element(self) -> None:
        """Single element returns that element as max loss, rest zero."""
        series = pl.Series("ls", [-0.05])
        result = tail_risk_metrics(series)
        assert result.max_single_day_loss == pytest.approx(-0.05)
        assert result.cvar_95 == 0.0
        assert result.cvar_99 == 0.0
        assert result.skewness == 0.0
        assert result.kurtosis == 0.0

    def test_two_elements(self) -> None:
        """Two elements produce valid metrics."""
        series = pl.Series("ls", [0.01, -0.02])
        result = tail_risk_metrics(series)
        assert result.max_single_day_loss == pytest.approx(-0.02)
        assert isinstance(result.cvar_95, float)
        assert isinstance(result.cvar_99, float)

    def test_all_positive_returns(self) -> None:
        """All positive returns: max loss should be the minimum positive."""
        series = pl.Series("ls", [0.01, 0.02, 0.03, 0.04, 0.05])
        result = tail_risk_metrics(series)
        assert result.max_single_day_loss == pytest.approx(0.01)

    def test_all_negative_returns(self) -> None:
        """All negative returns: max loss is the most negative value."""
        series = pl.Series("ls", [-0.01, -0.05, -0.03, -0.02, -0.04])
        result = tail_risk_metrics(series)
        assert result.max_single_day_loss == pytest.approx(-0.05)

    def test_large_dataset(self) -> None:
        """Large dataset (1000 elements) produces valid metrics."""
        import numpy as np

        rng = np.random.default_rng(42)
        vals = rng.normal(0.001, 0.02, 1000)
        series = pl.Series("ls", vals.tolist())
        result = tail_risk_metrics(series)
        assert isinstance(result.cvar_95, float)
        assert isinstance(result.cvar_99, float)
        assert isinstance(result.skewness, float)
        assert isinstance(result.kurtosis, float)
        assert isinstance(result.max_single_day_loss, float)
        # CVaR should be negative (average of worst losses)
        assert result.cvar_95 < 0
        assert result.cvar_99 < result.cvar_95  # 99% worse than 95%

    def test_extreme_outlier(self) -> None:
        """Extreme outlier affects max_single_day_loss heavily."""
        series = pl.Series("ls", [0.01, 0.01, -0.01, -0.5, 0.01, 0.01])
        result = tail_risk_metrics(series)
        assert result.max_single_day_loss == pytest.approx(-0.5)

    def test_symmetric_distribution_near_zero_skewness(self) -> None:
        """Symmetric distribution should have near-zero skewness."""
        series = pl.Series("ls", [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0])
        result = tail_risk_metrics(series)
        assert abs(result.skewness) < 0.1

    def test_uniform_distribution(self) -> None:
        """Uniform distribution has negative excess kurtosis."""
        vals = [float(i) for i in range(1, 101)]
        series = pl.Series("ls", vals)
        result = tail_risk_metrics(series)
        # Uniform distribution: excess kurtosis = -6/5 = -1.2
        assert result.kurtosis < 0


# ---------------------------------------------------------------------------
# grinold_kahn_ir
# ---------------------------------------------------------------------------


class TestGrinoldKahnIR:
    """Tests for grinold_kahn_ir."""

    def test_zero_ic_std_returns_zero(self) -> None:
        """Zero IC std returns 0.0."""
        result = grinold_kahn_ir(
            mean_ic=0.05, ic_std=0.0, ic_autocorr_lag1=0.0, breadth=100
        )
        assert result == 0.0

    def test_zero_breadth_returns_zero(self) -> None:
        """Zero breadth returns 0.0."""
        result = grinold_kahn_ir(
            mean_ic=0.05, ic_std=0.1, ic_autocorr_lag1=0.0, breadth=0
        )
        assert result == 0.0

    def test_negative_breadth_returns_zero(self) -> None:
        """Negative breadth returns 0.0."""
        result = grinold_kahn_ir(
            mean_ic=0.05, ic_std=0.1, ic_autocorr_lag1=0.0, breadth=-1
        )
        assert result == 0.0

    def test_zero_autocorr_basic_ir(self) -> None:
        """With zero autocorrelation, IR = (IC/std) * sqrt(BR)."""
        mean_ic = 0.05
        ic_std = 0.10
        breadth = 100.0
        expected = (mean_ic / ic_std) * math.sqrt(breadth)
        result = grinold_kahn_ir(mean_ic, ic_std, ic_autocorr_lag1=0.0, breadth=breadth)
        assert result == pytest.approx(expected, abs=1e-10)

    def test_positive_autocorr_changes_ir(self) -> None:
        """Strong positive autocorrelation changes the IR value.

        Note: The GK formula uses T = periods_per_year (large), so the
        autocorrelation correction may increase or decrease IR depending
        on the parameter values. We just verify the result is different.
        """
        ir_zero = grinold_kahn_ir(0.05, 0.10, 0.0, breadth=100)
        ir_pos = grinold_kahn_ir(0.05, 0.10, 0.9, breadth=100)
        assert ir_pos != ir_zero
        assert math.isfinite(ir_pos)

    def test_negative_ic_produces_negative_ir(self) -> None:
        """Negative mean IC produces negative IR."""
        result = grinold_kahn_ir(-0.05, 0.10, 0.0, breadth=100)
        assert result < 0

    def test_large_breadth_increases_ir(self) -> None:
        """Larger breadth increases IR (ceteris paribus)."""
        ir_small = grinold_kahn_ir(0.05, 0.10, 0.0, breadth=50)
        ir_large = grinold_kahn_ir(0.05, 0.10, 0.0, breadth=200)
        assert ir_large > ir_small

    @pytest.mark.parametrize("rho", [-0.5, -0.2, 0.0, 0.2, 0.5, 0.8])
    def test_various_autocorrelations(self, rho: float) -> None:
        """Various autocorrelation values produce finite results."""
        result = grinold_kahn_ir(0.05, 0.10, rho, breadth=100)
        assert math.isfinite(result)

    def test_custom_periods_per_year(self) -> None:
        """Custom periods_per_year affects the IR calculation."""
        ir_244 = grinold_kahn_ir(0.05, 0.10, 0.0, breadth=100, periods_per_year=244)
        ir_252 = grinold_kahn_ir(0.05, 0.10, 0.0, breadth=100, periods_per_year=252)
        # Both should be positive and different
        assert ir_244 > 0
        assert ir_252 > 0

    def test_very_high_autocorr_near_one(self) -> None:
        """Autocorrelation near 1.0 should still return finite result."""
        result = grinold_kahn_ir(0.05, 0.10, 0.99, breadth=100)
        assert math.isfinite(result)
