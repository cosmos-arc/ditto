"""Unit tests for performance attribution (EVAL-EV-9)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_engine.engine.evaluation.metrics import performance_attribution
from ditto_engine.engine.evaluation.report import PerformanceAttributionResult

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_quantile_ret_df(
    n_dates: int = 100,
    n_quantiles: int = 5,
    *,
    seed: int = 42,
    top_return_bias: float = 0.002,
) -> pl.DataFrame:
    """Create synthetic quantile return DataFrame with monotonic quantile returns.

    Higher quantiles have slightly higher mean returns (positive factor).
    """
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    rows: list[dict[str, object]] = []
    for d in dates:
        for q in range(1, n_quantiles + 1):
            # Linear bias: top quantile has higher average return
            bias = top_return_bias * (q - 1) / max(n_quantiles - 1, 1)
            mean_ret = bias + rng.normal(0, 0.01)
            rows.append(
                {
                    "trade_date": d,
                    "quantile": q,
                    "mean_return": mean_ret,
                    "count": 10,
                },
            )
    return pl.DataFrame(rows)


def _make_known_quantile_ret_df() -> pl.DataFrame:
    """Create quantile return DataFrame with deterministic values.

    2 quantiles, 10 dates. Q1 returns 0.001 daily, Q2 returns 0.002 daily.
    All returns are positive so win rates should be 1.0.
    """
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(10)]
    rows: list[dict[str, object]] = []
    for d in dates:
        rows.append({"trade_date": d, "quantile": 1, "mean_return": 0.001, "count": 10})
        rows.append({"trade_date": d, "quantile": 2, "mean_return": 0.002, "count": 10})
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# performance_attribution
# ---------------------------------------------------------------------------


class TestPerformanceAttribution:
    """Tests for performance_attribution."""

    def test_alpha_and_ir_known_values(self) -> None:
        """Known quantile returns verify alpha and IR.

        Q1: 0.001 daily, Q2: 0.002 daily. LS spread = 0.001 daily.
        Annualized LS return = 0.001 * 244 = 0.244.
        """
        df = _make_known_quantile_ret_df()
        result = performance_attribution(df, periods_per_year=244)

        # selection_return = LS spread annualized = (0.002 - 0.001) * 244 = 0.244
        assert isinstance(result, PerformanceAttributionResult)
        assert result.selection_return == pytest.approx(0.244, rel=0.01)

        # annual_alpha = selection_return (simplified)
        assert result.annual_alpha == pytest.approx(result.selection_return, rel=0.01)

        # tracking_error = std(LS daily) * sqrt(244). Since LS is constant,
        # std is near-zero (floating-point residual)
        assert result.tracking_error == pytest.approx(0.0, abs=1e-10)

    def test_win_rate_by_quantile(self) -> None:
        """Fraction of positive days per quantile should be correct.

        With all positive returns (0.001 for Q1, 0.002 for Q2), win rates should be 1.0.
        """
        df = _make_known_quantile_ret_df()
        result = performance_attribution(df)

        assert result.win_rate_by_quantile[1] == pytest.approx(1.0)
        assert result.win_rate_by_quantile[2] == pytest.approx(1.0)

    def test_empty_data(self) -> None:
        """Empty data should return all zeros."""
        df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "quantile": pl.Int64,
                "mean_return": pl.Float64,
            },
        )
        result = performance_attribution(df)

        assert result.total_return == 0.0
        assert result.selection_return == 0.0
        assert result.timing_return == 0.0
        assert result.interaction_return == 0.0
        assert result.annual_alpha == 0.0
        assert result.tracking_error == 0.0
        assert result.information_ratio == 0.0
        assert result.win_rate_by_quantile == {}

    def test_performance_attribution_result_type(self) -> None:
        """Result should be a frozen dataclass."""
        df = _make_quantile_ret_df()
        result = performance_attribution(df)

        assert isinstance(result, PerformanceAttributionResult)
        # Verify frozen
        with pytest.raises(AttributeError):
            result.total_return = 99.0  # type: ignore[misc]

    def test_mixed_positive_negative_returns(self) -> None:
        """With mixed returns, win_rate should be between 0 and 1."""
        rng = np.random.default_rng(42)
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(50)]
        rows: list[dict[str, object]] = []
        for d in dates:
            for q in [1, 2]:
                mean_ret = rng.normal(0, 0.01)
                rows.append(
                    {
                        "trade_date": d,
                        "quantile": q,
                        "mean_return": mean_ret,
                        "count": 10,
                    },
                )
        df = pl.DataFrame(rows)
        result = performance_attribution(df)

        for _q, wr in result.win_rate_by_quantile.items():
            assert 0.0 <= wr <= 1.0

    def test_interaction_return_is_zero(self) -> None:
        """interaction_return should always be 0.0 (simplified)."""
        df = _make_quantile_ret_df()
        result = performance_attribution(df)
        assert result.interaction_return == 0.0

    def test_total_return_equals_annualized_average(self) -> None:
        """total_return should equal annualized equal-weighted average."""
        df = _make_known_quantile_ret_df()
        result = performance_attribution(df, periods_per_year=244)

        # Average daily return across quantiles = (0.001 + 0.002) / 2 = 0.0015
        # Annualized = 0.0015 * 244 = 0.366
        assert result.total_return == pytest.approx(0.366, rel=0.01)

    def test_ir_zero_when_tracking_error_zero(self) -> None:
        """When tracking_error is ~0, information_ratio should be 0."""
        df = _make_known_quantile_ret_df()
        result = performance_attribution(df)
        assert result.tracking_error == pytest.approx(0.0, abs=1e-10)
        # When TE is effectively zero, IR should be zero (not infinity)
        assert result.information_ratio == 0.0
