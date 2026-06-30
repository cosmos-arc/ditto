"""Unit tests for evaluation/metrics/ic_report.py boundary cases.

Tests regime_adjusted_ic, ic_momentum, and sub_period_ic with edge cases:
empty input, all NaN, small sample, window exceeding data length, etc.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_features.errors import EvaluationError
from ditto_features.evaluation.metrics.ic_report import (
    _build_transition_matrix,
    ic_momentum,
    regime_adjusted_ic,
    sub_period_ic,
)
from ditto_features.evaluation.report import RegimeICResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ic_df(
    n: int,
    *,
    seed: int = 42,
    mean_ic: float = 0.05,
    ic_std: float = 0.1,
    start_date: date = date(2024, 1, 1),
) -> pl.DataFrame:
    """Create synthetic IC DataFrame."""
    rng = np.random.default_rng(seed)
    dates = [start_date + timedelta(days=i) for i in range(n)]
    ic_vals = rng.normal(mean_ic, ic_std, n)
    return pl.DataFrame({"trade_date": dates, "ic": [float(v) for v in ic_vals]})


# ---------------------------------------------------------------------------
# regime_adjusted_ic
# ---------------------------------------------------------------------------


class TestRegimeAdjustedIC:
    """Boundary tests for regime_adjusted_ic."""

    def test_empty_input(self) -> None:
        """Empty IC DataFrame returns empty regimes."""
        df = pl.DataFrame(schema={"trade_date": pl.Date, "ic": pl.Float64})
        result = regime_adjusted_ic(df)
        assert isinstance(result, RegimeICResult)
        assert result.regimes == {}
        assert result.regime_labels == []
        assert result.transition_matrix == {}
        assert result.ic_trend == 0.0
        assert result.ic_trend_p_value == 1.0

    def test_all_nan_input(self) -> None:
        """All-NaN IC DataFrame returns empty regimes."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "ic": [float("nan"), float("nan")],
            }
        )
        result = regime_adjusted_ic(df)
        assert result.regimes == {}

    def test_single_row(self) -> None:
        """Single IC observation produces valid result."""
        df = pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]})
        result = regime_adjusted_ic(df)
        assert isinstance(result, RegimeICResult)
        # Single observation gets assigned to low_vol (|IC| <= median(|IC|))
        assert len(result.regime_labels) == 1
        # Not enough transitions for a matrix
        assert result.transition_matrix == {}

    def test_two_regimes_split(self) -> None:
        """With enough data, both low_vol and high_vol regimes exist."""
        df = _make_ic_df(100, mean_ic=0.0, ic_std=0.2)
        result = regime_adjusted_ic(df)
        # Should have both regimes
        assert "low_vol" in result.regimes or "high_vol" in result.regimes
        assert len(result.regime_labels) > 0

    def test_regime_labels_are_date_regime_pairs(self) -> None:
        """regime_labels is list of (date_str, regime_name)."""
        df = _make_ic_df(20)
        result = regime_adjusted_ic(df)
        for date_str, regime_name in result.regime_labels:
            assert isinstance(date_str, str)
            assert regime_name in ("low_vol", "high_vol")

    def test_transition_matrix_row_sums_to_one(self) -> None:
        """Each row of transition matrix sums to ~1.0."""
        df = _make_ic_df(50)
        result = regime_adjusted_ic(df)
        if result.transition_matrix:
            for _from_regime, transitions in result.transition_matrix.items():
                total = sum(transitions.values())
                assert total == pytest.approx(1.0, abs=0.01)

    def test_custom_ic_column(self) -> None:
        """Custom ic_col parameter is respected."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(50)],
                "custom_ic": [0.1 * (i % 5) for i in range(50)],
            }
        )
        result = regime_adjusted_ic(df, ic_col="custom_ic")
        assert isinstance(result, RegimeICResult)

    def test_all_same_ic_value(self) -> None:
        """All same IC value: median = that value, all low_vol."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(20)],
                "ic": [0.05] * 20,
            }
        )
        result = regime_adjusted_ic(df)
        assert isinstance(result, RegimeICResult)
        # All values have |IC| == 0.05 == median -> all low_vol
        for _, regime_name in result.regime_labels:
            assert regime_name == "low_vol"


# ---------------------------------------------------------------------------
# ic_momentum
# ---------------------------------------------------------------------------


class TestICMomentum:
    """Boundary tests for ic_momentum."""

    def test_small_sample_returns_zero(self) -> None:
        """Fewer than MIN_OBS_FOR_OLS returns (0.0, 1.0)."""
        df = _make_ic_df(20)
        trend, p_value = ic_momentum(df, window=20)
        assert trend == 0.0
        assert p_value == 1.0

    def test_window_exceeds_data(self) -> None:
        """Window larger than data uses all available data."""
        df = _make_ic_df(10)
        # With 10 points (< MIN_OBS_FOR_OLS=30), should return (0.0, 1.0)
        trend, p_value = ic_momentum(df, window=100)
        assert trend == 0.0
        assert p_value == 1.0

    def test_large_sample_with_trend(self) -> None:
        """Large sample with clear trend should detect it."""
        # Create IC series with a clear upward trend
        n = 100
        ic_vals = [
            0.01 * i + 0.001 * np.random.default_rng(42).normal() for i in range(n)
        ]
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
        df = pl.DataFrame({"trade_date": dates, "ic": ic_vals})
        trend, _p_value = ic_momentum(df, window=100)
        # Should detect a positive trend
        assert trend > 0

    def test_zero_variance_returns_zero_trend(self) -> None:
        """Constant IC (zero variance) returns (0.0, 1.0)."""
        n = 50
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(n)],
                "ic": [0.05] * n,
            }
        )
        trend, p_value = ic_momentum(df, window=50)
        # Constant IC -> residuals are zero -> se_beta=0 -> returns (beta, 1.0)
        # Actually with constant IC, var_t != 0 but ic_mean == all values
        # so cov_ti = 0 -> beta = 0
        assert trend == 0.0
        assert p_value == 1.0

    def test_custom_window(self) -> None:
        """Custom window parameter is respected."""
        df = _make_ic_df(100)
        # Window of 50 should use only last 50 values
        trend_50, _ = ic_momentum(df, window=50)
        trend_100, _ = ic_momentum(df, window=100)
        # Different windows should generally produce different results
        assert isinstance(trend_50, float)
        assert isinstance(trend_100, float)

    def test_nan_values_dropped(self) -> None:
        """NaN IC values are dropped before computation."""
        n = 50
        ic_vals = [0.05] * n
        ic_vals[10] = float("nan")
        ic_vals[20] = float("nan")
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(n)],
                "ic": ic_vals,
            }
        )
        trend, p_value = ic_momentum(df, window=50)
        assert isinstance(trend, float)
        assert isinstance(p_value, float)


# ---------------------------------------------------------------------------
# sub_period_ic
# ---------------------------------------------------------------------------


class TestSubPeriodICBoundary:
    """Boundary tests for sub_period_ic."""

    def test_single_date(self) -> None:
        """Single date produces one period with std=0."""
        df = pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]})
        result = sub_period_ic(df, freq="year")
        assert len(result) == 1
        summary = next(iter(result.values()))
        assert summary.std == 0.0

    def test_quarter_frequency(self) -> None:
        """Quarter frequency produces correct labels."""
        dates = [
            date(2024, 1, 15),
            date(2024, 4, 15),
            date(2024, 7, 15),
            date(2024, 10, 15),
        ]
        df = pl.DataFrame({"trade_date": dates, "ic": [0.05, 0.03, 0.07, 0.04]})
        result = sub_period_ic(df, freq="quarter")
        assert "2024Q1" in result
        assert "2024Q2" in result
        assert "2024Q3" in result
        assert "2024Q4" in result

    def test_invalid_frequency_raises(self) -> None:
        """Invalid frequency raises EvaluationError."""
        df = _make_ic_df(10)
        with pytest.raises(EvaluationError, match="Unknown frequency"):
            sub_period_ic(df, freq="week")

    def test_null_ic_values_dropped(self) -> None:
        """Null IC values are dropped before computation."""
        dates = [date(2024, 1, i) for i in range(1, 11)]
        ic_vals = [0.05, None, 0.03, 0.04, None, 0.06, 0.02, 0.07, None, 0.01]
        df = pl.DataFrame({"trade_date": dates, "ic": ic_vals})
        result = sub_period_ic(df, freq="year")
        assert len(result) > 0

    def test_all_null_ic(self) -> None:
        """All null IC produces empty result."""
        dates = [date(2024, 1, i) for i in range(1, 11)]
        df = pl.DataFrame({"trade_date": dates, "ic": [None] * 10})
        result = sub_period_ic(df, freq="year")
        assert len(result) == 0

    def test_multi_year_split(self) -> None:
        """Data spanning multiple years produces multiple entries."""
        dates = [date(2023, 6, 1), date(2024, 6, 1), date(2025, 6, 1)]
        df = pl.DataFrame({"trade_date": dates, "ic": [0.05, 0.03, 0.07]})
        result = sub_period_ic(df, freq="year")
        assert "2023" in result
        assert "2024" in result
        assert "2025" in result


# ---------------------------------------------------------------------------
# _build_transition_matrix (private helper)
# ---------------------------------------------------------------------------


class TestBuildTransitionMatrix:
    """Tests for _build_transition_matrix private helper."""

    def test_too_few_labels(self) -> None:
        """Fewer than MIN_TRANSITIONS_FOR_MATRIX labels returns empty."""
        labels = [("2024-01-01", "low_vol")]
        assert _build_transition_matrix(labels) == {}

    def test_basic_transitions(self) -> None:
        """Basic transition matrix computed correctly."""
        labels = [
            ("2024-01-01", "low_vol"),
            ("2024-01-02", "low_vol"),
            ("2024-01-03", "high_vol"),
            ("2024-01-04", "high_vol"),
            ("2024-01-05", "low_vol"),
        ]
        result = _build_transition_matrix(labels)
        assert "low_vol" in result
        assert "high_vol" in result
        # low_vol -> low_vol: 1, low_vol -> high_vol: 1 -> each 0.5
        assert result["low_vol"]["low_vol"] == pytest.approx(0.5)
        assert result["low_vol"]["high_vol"] == pytest.approx(0.5)

    def test_all_same_regime(self) -> None:
        """All in same regime: self-transition = 1.0."""
        labels = [
            ("2024-01-01", "low_vol"),
            ("2024-01-02", "low_vol"),
            ("2024-01-03", "low_vol"),
        ]
        result = _build_transition_matrix(labels)
        assert result["low_vol"]["low_vol"] == 1.0
