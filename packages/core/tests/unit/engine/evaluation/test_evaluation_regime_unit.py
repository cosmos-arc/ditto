"""Unit tests for regime-adjusted IC and IC trend (EVAL-EV-5, EVAL-EV-10)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
from ditto_core.engine.evaluation.metrics import (
    ic_momentum,
    regime_adjusted_ic,
)
from ditto_core.engine.evaluation.report import RegimeICResult

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_regime_ic_df(
    n_dates: int = 100,
    *,
    seed: int = 42,
) -> pl.DataFrame:
    """Create synthetic IC series with alternating high/low volatility regimes.

    First half: low volatility (|IC| small), second half: high volatility (|IC| large).
    """
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    ic_vals: list[float] = []
    half = n_dates // 2
    for i in range(n_dates):
        if i < half:
            ic_vals.append(float(rng.normal(0.02, 0.03)))
        else:
            ic_vals.append(float(rng.normal(0.10, 0.15)))
    return pl.DataFrame({"trade_date": dates, "ic": ic_vals})


def _make_trending_ic_df(
    n_dates: int = 100,
    *,
    seed: int = 42,
    slope: float = 0.001,
) -> pl.DataFrame:
    """Create synthetic IC series with a linear trend.

    ic_t = intercept + slope * t + noise
    """
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    ic_vals = [float(0.01 + slope * i + rng.normal(0, 0.02)) for i in range(n_dates)]
    return pl.DataFrame({"trade_date": dates, "ic": ic_vals})


# ---------------------------------------------------------------------------
# regime_adjusted_ic
# ---------------------------------------------------------------------------


class TestRegimeAdjustedIC:
    """Tests for regime_adjusted_ic."""

    def test_two_regimes_synthetic_ic(self) -> None:
        """Synthetic IC with high/low volatility periods yields two regimes."""
        df = _make_regime_ic_df(n_dates=100, seed=42)
        result = regime_adjusted_ic(df, n_regimes=2)

        assert isinstance(result, RegimeICResult)
        assert len(result.regimes) == 2
        assert "low_vol" in result.regimes
        assert "high_vol" in result.regimes

        # High-vol regime should have higher IC std than low-vol
        low_std = result.regimes["low_vol"].std
        high_std = result.regimes["high_vol"].std
        assert high_std >= low_std

    def test_regime_labels_match_dates(self) -> None:
        """Regime labels should have one entry per date."""
        df = _make_regime_ic_df(n_dates=100)
        result = regime_adjusted_ic(df, n_regimes=2)

        assert len(result.regime_labels) == df.height
        # Each entry should be (date_str, regime_label)
        for label_tuple in result.regime_labels:
            assert isinstance(label_tuple, tuple)
            assert len(label_tuple) == 2

    def test_transition_matrix_structure(self) -> None:
        """Transition matrix should be {from: {to: probability}}."""
        df = _make_regime_ic_df(n_dates=100)
        result = regime_adjusted_ic(df, n_regimes=2)

        assert isinstance(result.transition_matrix, dict)
        for from_regime, to_dict in result.transition_matrix.items():
            assert from_regime in ("low_vol", "high_vol")
            assert isinstance(to_dict, dict)
            for to_regime, prob in to_dict.items():
                assert to_regime in ("low_vol", "high_vol")
                assert 0.0 <= prob <= 1.0

    def test_ic_trend_from_regime(self) -> None:
        """ic_trend and ic_trend_p_value should be floats."""
        df = _make_regime_ic_df(n_dates=100)
        result = regime_adjusted_ic(df, n_regimes=2)

        assert isinstance(result.ic_trend, float)
        assert isinstance(result.ic_trend_p_value, float)
        assert 0.0 <= result.ic_trend_p_value <= 1.0

    def test_regime_empty(self) -> None:
        """Empty IC DataFrame should return all zeros."""
        df = pl.DataFrame(schema={"trade_date": pl.Date, "ic": pl.Float64})
        result = regime_adjusted_ic(df, n_regimes=2)

        assert isinstance(result, RegimeICResult)
        assert result.regimes == {}
        assert result.regime_labels == []
        assert result.transition_matrix == {}
        assert result.ic_trend == 0.0
        assert result.ic_trend_p_value == 1.0

    def test_regime_single_date(self) -> None:
        """Single date IC should still produce a result (one regime)."""
        df = pl.DataFrame({"trade_date": [date(2024, 1, 2)], "ic": [0.05]})
        result = regime_adjusted_ic(df, n_regimes=2)

        assert isinstance(result, RegimeICResult)
        # With single date, all goes to one regime based on median threshold
        assert len(result.regimes) >= 1
        assert len(result.regime_labels) == 1


# ---------------------------------------------------------------------------
# ic_momentum
# ---------------------------------------------------------------------------


class TestICMomentum:
    """Tests for ic_momentum."""

    def test_ic_trend_increasing(self) -> None:
        """Monotonically increasing IC should yield a positive trend."""
        df = _make_trending_ic_df(n_dates=100, slope=0.002)
        trend, p_value = ic_momentum(df, window=100)

        assert isinstance(trend, float)
        assert isinstance(p_value, float)
        assert trend > 0  # positive slope for increasing series

    def test_ic_trend_flat(self) -> None:
        """Flat IC (no trend) should yield near-zero trend slope."""
        rng = np.random.default_rng(42)
        n = 100
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n)]
        ic_vals = [float(rng.normal(0.05, 0.01)) for _ in range(n)]
        df = pl.DataFrame({"trade_date": dates, "ic": ic_vals})

        trend, _p_value = ic_momentum(df, window=100)

        assert isinstance(trend, float)
        assert abs(trend) < 0.001  # near-zero slope

    def test_ic_trend_declining(self) -> None:
        """Declining IC should yield a negative trend."""
        df = _make_trending_ic_df(n_dates=100, slope=-0.002)
        trend, _p_value = ic_momentum(df, window=100)

        assert isinstance(trend, float)
        assert trend < 0  # negative slope for declining series

    def test_window_truncates_data(self) -> None:
        """Window parameter should truncate to last N values."""
        df = _make_trending_ic_df(n_dates=200, slope=0.002)
        trend_full, _ = ic_momentum(df, window=200)
        trend_half, _ = ic_momentum(df, window=100)

        # Using only last 100 should capture the trend but may differ
        # from using all 200
        assert isinstance(trend_full, float)
        assert isinstance(trend_half, float)

    def test_small_data_returns_zero(self) -> None:
        """Small data (n <= 30) should return (0.0, 1.0)."""
        rng = np.random.default_rng(42)
        n = 10
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n)]
        ic_vals = [float(rng.normal(0.05, 0.02)) for _ in range(n)]
        df = pl.DataFrame({"trade_date": dates, "ic": ic_vals})

        trend, p_value = ic_momentum(df, window=10)
        assert trend == 0.0
        assert p_value == 1.0

    def test_empty_data(self) -> None:
        """Empty DataFrame should return (0.0, 1.0)."""
        df = pl.DataFrame(schema={"trade_date": pl.Date, "ic": pl.Float64})
        trend, p_value = ic_momentum(df, window=60)
        assert trend == 0.0
        assert p_value == 1.0
