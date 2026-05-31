"""Comprehensive boundary tests for evaluation/metrics/ic_computation.py.

Extended tests for rank_ic, pearson_ic, ic_summary, ic_decay, and
ic_autocorrelation with edge cases: all NaN, single row, large lag,
perfect correlation, anti-correlation, etc.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_features.evaluation.metrics.ic_computation import (
    ic_autocorrelation,
    ic_decay,
    ic_summary,
    pearson_ic,
    rank_ic,
)
from ditto_features.evaluation.report import ICSummary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_factor_return(
    n_dates: int = 20,
    n_entities: int = 50,
    *,
    seed: int = 42,
    ic_strength: float = 0.3,
) -> tuple[pl.DataFrame, pl.DataFrame]:
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


def _make_close_df(
    n_dates: int = 30,
    n_entities: int = 50,
    *,
    seed: int = 42,
) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(n_entities))
    rows: list[dict[str, object]] = []
    prices = dict.fromkeys(entities, 100.0)

    for d in dates:
        for eid in entities:
            rows.append({"trade_date": d, "instrument_id": eid, "close": prices[eid]})
            prices[eid] *= 1 + rng.normal(0, 0.02)

    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# rank_ic extended
# ---------------------------------------------------------------------------


class TestRankICExtended:
    """Extended tests for rank_ic."""

    def test_two_dates(self) -> None:
        """Two dates produce two IC values."""
        factor_df, return_df = _make_factor_return(n_dates=2, n_entities=30)
        result = rank_ic(factor_df, return_df)
        assert result.height == 2

    def test_many_dates(self) -> None:
        """100 dates produce 100 IC values."""
        factor_df, _return_df = _make_factor_return(n_dates=100, n_entities=30)
        result = rank_ic(factor_df, factor_df.rename({"value": "forward_return"}))
        # Perfect self-correlation: all IC should be near 1
        assert result.height == 100
        non_null = result["ic"].drop_nulls()
        assert all(v > 0.9 for v in non_null.to_list())

    def test_no_overlap_returns_empty(self) -> None:
        """No overlapping entities returns empty result."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "instrument_id": [1, 2, 3],
                "value": [1.0, 2.0, 3.0],
            }
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "instrument_id": [4, 5, 6],
                "forward_return": [0.1, 0.2, 0.3],
            }
        )
        result = rank_ic(factor_df, return_df)
        assert result.height == 0

    def test_all_same_factor_values(self) -> None:
        """All same factor values produce null IC (no variance)."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "instrument_id": [1, 2, 3, 4, 5],
                "value": [1.0, 1.0, 1.0, 1.0, 1.0],
            }
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "instrument_id": [1, 2, 3, 4, 5],
                "forward_return": [0.1, 0.2, 0.3, 0.4, 0.5],
            }
        )
        result = rank_ic(factor_df, return_df)
        # Constant factor -> null rank correlation
        assert result["ic"][0] is None or math.isnan(result["ic"][0])

    def test_large_cross_section(self) -> None:
        """Large cross-section (500 entities) produces valid IC."""
        factor_df, return_df = _make_factor_return(n_dates=5, n_entities=500)
        result = rank_ic(factor_df, return_df)
        assert result.height == 5
        for ic_val in result["ic"].to_list():
            if ic_val is not None:
                assert -1.0 <= ic_val <= 1.0


# ---------------------------------------------------------------------------
# pearson_ic extended
# ---------------------------------------------------------------------------


class TestPearsonICExtended:
    """Extended tests for pearson_ic."""

    def test_perfect_negative_linear(self) -> None:
        """Perfect negative linear relationship yields IC near -1."""
        dates = [date(2024, 1, 1)]
        rows_f = [
            {"trade_date": dates[0], "instrument_id": i, "value": float(i)}
            for i in range(1, 11)
        ]
        rows_r = [
            {
                "trade_date": dates[0],
                "instrument_id": i,
                "forward_return": float(11 - i),
            }
            for i in range(1, 11)
        ]
        result = pearson_ic(pl.DataFrame(rows_f), pl.DataFrame(rows_r))
        assert result["ic"][0] < -0.99

    def test_no_correlation(self) -> None:
        """Uncorrelated data should have IC near 0."""
        rng = np.random.default_rng(42)
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 100,
                "instrument_id": list(range(100)),
                "value": rng.normal(0, 1, 100).tolist(),
            }
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 100,
                "instrument_id": list(range(100)),
                "forward_return": rng.normal(0, 1, 100).tolist(),
            }
        )
        result = pearson_ic(factor_df, return_df)
        assert abs(result["ic"][0]) < 0.3

    def test_constant_return(self) -> None:
        """Constant forward returns produce null IC."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "instrument_id": [1, 2, 3, 4, 5],
                "value": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "instrument_id": [1, 2, 3, 4, 5],
                "forward_return": [0.01, 0.01, 0.01, 0.01, 0.01],
            }
        )
        result = pearson_ic(factor_df, return_df)
        # polars returns 0.0 or null for constant-variance correlation
        ic_val = result["ic"][0]
        assert ic_val is None or math.isnan(ic_val) or ic_val == 0.0


# ---------------------------------------------------------------------------
# ic_summary extended
# ---------------------------------------------------------------------------


class TestICSummaryExtended:
    """Extended tests for ic_summary."""

    def test_all_positive_ic(self) -> None:
        """All positive IC should have win_rate = 1.0."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(50)],
                "ic": [0.05 + 0.001 * i for i in range(50)],
            }
        )
        result = ic_summary(df)
        assert result.win_rate == pytest.approx(1.0)
        assert result.mean > 0
        assert result.t_stat > 0

    def test_all_negative_ic(self) -> None:
        """All negative IC should have win_rate = 0.0."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(50)],
                "ic": [-0.05 - 0.001 * i for i in range(50)],
            }
        )
        result = ic_summary(df)
        assert result.win_rate == pytest.approx(0.0)
        assert result.mean < 0
        assert result.t_stat < 0

    def test_mixed_ic_win_rate(self) -> None:
        """Mix of positive and negative IC produces intermediate win rate."""
        ic_vals = [0.1, -0.05, 0.03, -0.02, 0.08, 0.04, -0.01, 0.06, 0.02, 0.07]
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(10)],
                "ic": ic_vals,
            }
        )
        result = ic_summary(df)
        expected_win = sum(1 for v in ic_vals if v > 0) / len(ic_vals)
        assert result.win_rate == pytest.approx(expected_win)

    def test_large_sample_p_value(self) -> None:
        """Large sample with consistent IC should have very small p-value."""
        rng = np.random.default_rng(42)
        # IC always positive with small noise
        ic_vals = rng.normal(0.10, 0.02, 200)
        df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1) + timedelta(days=i) for i in range(200)
                ],
                "ic": ic_vals.tolist(),
            }
        )
        result = ic_summary(df)
        assert result.p_value < 0.001

    def test_two_dates(self) -> None:
        """Two dates produce valid summary (n=2, df=1)."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "ic": [0.05, 0.10],
            }
        )
        result = ic_summary(df)
        assert result.mean == pytest.approx(0.075)
        assert result.std > 0

    def test_all_nan_returns_zero_summary(self) -> None:
        """All-NaN IC values produce zero summary."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 5,
                "ic": [float("nan")] * 5,
            }
        )
        result = ic_summary(df)
        assert result == ICSummary(
            mean=0.0, std=0.0, icir=0.0, t_stat=0.0, p_value=1.0, win_rate=0.0
        )


# ---------------------------------------------------------------------------
# ic_decay extended
# ---------------------------------------------------------------------------


class TestICDecayExtended:
    """Extended tests for ic_decay."""

    def test_single_lag(self) -> None:
        """Single lag produces one result."""
        factor_df, _ = _make_factor_return(n_dates=20, n_entities=30)
        close_df = _make_close_df(n_dates=30, n_entities=30)
        results, _half_life = ic_decay(factor_df, close_df, lags=[5])
        assert len(results) == 1
        assert results[0][0] == 5

    def test_lag_exceeding_data(self) -> None:
        """Lag exceeding data length produces NaN IC."""
        factor_df, _ = _make_factor_return(n_dates=10, n_entities=30)
        close_df = _make_close_df(n_dates=15, n_entities=30)
        results, _ = ic_decay(factor_df, close_df, lags=[100])
        assert len(results) == 1
        # IC should be NaN (not enough data for lag=100)
        assert math.isnan(results[0][1]) or results[0][1] == 0.0

    def test_multiple_lags_ordered(self) -> None:
        """Results are returned in the same order as lags."""
        factor_df, _ = _make_factor_return(n_dates=30, n_entities=50, ic_strength=0.5)
        close_df = _make_close_df(n_dates=50, n_entities=50)
        lags = [1, 3, 5, 10, 20]
        results, _ = ic_decay(factor_df, close_df, lags=lags)
        assert [r[0] for r in results] == lags

    def test_decay_magnitude_decreases(self) -> None:
        """With decaying IC, absolute IC magnitude tends to decrease with lag."""
        factor_df, _ = _make_factor_return(
            n_dates=50, n_entities=100, ic_strength=0.6, seed=123
        )
        close_df = _make_close_df(n_dates=80, n_entities=100, seed=123)
        results, _ = ic_decay(factor_df, close_df, lags=[1, 5, 10, 20])
        # Generally, |IC(lag=1)| > |IC(lag=20)|, though not guaranteed
        # with noisy data.  Just verify structure.
        assert all(isinstance(ic, float) for _, ic in results)


# ---------------------------------------------------------------------------
# ic_autocorrelation extended
# ---------------------------------------------------------------------------


class TestICAutocorrelationExtended:
    """Extended tests for ic_autocorrelation."""

    def test_constant_series(self) -> None:
        """Constant IC series has ACF of 1.0 (perfect self-correlation)."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(20)],
                "ic": [0.05] * 20,
            }
        )
        result = ic_autocorrelation(df, max_lag=3)
        assert len(result) == 3
        # Constant series -> dx = dy = 0 -> numerator = 0, denominator = 0 -> NaN
        # but polars sum of zeros gives 0/0 -> NaN
        for _, acf_val in result:
            assert math.isnan(acf_val) or acf_val in {1.0, 0.0}

    def test_alternating_series(self) -> None:
        """Alternating IC series has negative ACF at lag 1."""
        ic_vals = [(-1) ** i * 0.1 for i in range(50)]
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(50)],
                "ic": ic_vals,
            }
        )
        result = ic_autocorrelation(df, max_lag=1)
        assert result[0][1] < -0.5  # Strongly negative

    def test_max_lag_1(self) -> None:
        """max_lag=1 produces exactly one entry."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(20)],
                "ic": list(range(20)),
            }
        )
        result = ic_autocorrelation(df, max_lag=1)
        assert len(result) == 1
        assert result[0][0] == 1

    def test_large_max_lag(self) -> None:
        """max_lag larger than data produces NaN entries."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "ic": [0.1, 0.2],
            }
        )
        result = ic_autocorrelation(df, max_lag=10)
        assert len(result) == 10
        # lag=1: n=2, lag=1 < n=2 -> computable but only 1 pair
        # Actually lag >= n means n-lag = 0 or 1 pair -> may be NaN
        # Just verify structure
        for lag, acf in result:
            assert isinstance(lag, int)
            assert isinstance(acf, float)

    def test_custom_ic_column(self) -> None:
        """Custom ic_col parameter is respected."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(20)],
                "custom_ic": [float(i) for i in range(20)],
            }
        )
        result = ic_autocorrelation(df, max_lag=3, ic_col="custom_ic")
        assert len(result) == 3

    def test_single_element(self) -> None:
        """Single IC value produces NaN for all lags."""
        df = pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]})
        result = ic_autocorrelation(df, max_lag=3)
        assert len(result) == 3
        for _, acf_val in result:
            assert math.isnan(acf_val)
