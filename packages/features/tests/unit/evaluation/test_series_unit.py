"""Tests for factor evaluation per-date series derivations."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_features.evaluation.series import (
    ls_nav_series,
    monthly_ic,
    quantile_nav_series,
    rolling_ir_series,
)


def _ic_frame(values: list[float]) -> pl.DataFrame:
    dates = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(values))]
    return pl.DataFrame({"trade_date": dates, "ic": values})


def _q_ret_frame() -> pl.DataFrame:
    # 4 日 × 3 分位；q3 恒强、q1 恒弱 → 分位单调、LS 为正。
    rows = []
    for day in range(4):
        date = f"2026-01-0{day + 1}"
        for quantile, ret in ((1, -0.01), (2, 0.0), (3, 0.01)):
            rows.append(
                {
                    "trade_date": date,
                    "quantile": quantile,
                    "mean_return": ret,
                    "count": 10,
                },
            )
    return pl.DataFrame(rows)


class TestRollingIrSeries:
    def test_warmup_nulls_then_rolling_mean_over_std(self) -> None:
        # 样本口径 std(ddof=1)：[0.1,0.2,0.3] mean=0.2 std=0.1 → 2.0
        result = rolling_ir_series(_ic_frame([0.1, 0.2, 0.3, 0.4]), window=3)
        values = result["rolling_ir"].to_list()
        assert values[0] is None
        assert values[1] is None
        assert values[2] == pytest.approx(2.0)
        assert values[3] == pytest.approx(3.0)

    def test_rejects_window_below_two(self) -> None:
        with pytest.raises(ValueError, match="rolling IR window"):
            rolling_ir_series(_ic_frame([0.1]), window=1)


class TestQuantileNavSeries:
    def test_cumulative_nav_per_quantile_monotone_order(self) -> None:
        result = quantile_nav_series(_q_ret_frame(), n_quantiles=3)
        assert result.columns == ["trade_date", "q_1", "q_2", "q_3"]
        assert result["q_3"].to_list() == pytest.approx(
            [1.01, 1.01**2, 1.01**3, 1.01**4],
        )
        # 分位单调：q3 > q2 > q1（因子有区分度）
        for column_q1, column_q3 in zip(
            result["q_1"].to_list(),
            result["q_3"].to_list(),
            strict=True,
        ):
            assert column_q3 > column_q1

    def test_missing_quantile_column_fills_forward_null(self) -> None:
        partial = _q_ret_frame().filter(pl.col("quantile") != 2)
        result = quantile_nav_series(partial, n_quantiles=3)
        assert result["q_2"].to_list() == [None, None, None, None]


class TestLsNavSeries:
    def test_cumulative_long_short_nav_from_daily_spread(self) -> None:
        result = ls_nav_series(_q_ret_frame(), top_quantile=3, bottom_quantile=1)
        # 日 spread = 0.02 → 1.02^n
        assert result["ls_nav"].to_list() == pytest.approx(
            [1.02, 1.02**2, 1.02**3, 1.02**4],
        )


class TestMonthlyIc:
    def test_groups_by_year_month_with_count(self) -> None:
        frame = pl.DataFrame(
            {
                "trade_date": [
                    "2026-01-05",
                    "2026-01-20",
                    "2026-02-03",
                    "2025-12-30",
                ],
                "ic": [0.1, 0.3, -0.2, 0.0],
            },
        )
        result = monthly_ic(frame)
        assert result.to_dicts() == [
            {"year": 2025, "month": 12, "mean_ic": 0.0, "days": 1},
            {"year": 2026, "month": 1, "mean_ic": 0.2, "days": 2},
            {"year": 2026, "month": 2, "mean_ic": -0.2, "days": 1},
        ]
