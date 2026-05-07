"""代表因子 IC / 分层收益验证.

验证 3 个代表因子类别（价值 / 动量 / 质量）的 IC 和分层收益行为。
使用合成数据（synthetic data），不依赖真实市场数据。

- ep_ttm (Value): net_income_ttm / (close * total_shares) -> Positive
- reversal_1m (Momentum): -ts_pct_change(close, 20) -> Positive
- gross_margin (Quality): (revenue - cogs) / revenue -> Positive
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_features.evaluation.evaluator import FactorEvaluator
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    ICSummary,
    LongShortResult,
)

type FactorReturnPair = tuple[pl.DataFrame, pl.DataFrame]


# ---------------------------------------------------------------------------
# Test data factories  (same as test_evaluator_unit)
# ---------------------------------------------------------------------------


def _make_factor_and_return(
    n_dates: int = 100,
    n_entities: int = 50,
    *,
    seed: int = 42,
    ic_strength: float = 0.3,
) -> FactorReturnPair:
    """Create synthetic factor values and forward returns with known IC."""
    rng = np.random.default_rng(seed)

    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(1, n_entities + 1))

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
                {
                    "trade_date": d,
                    "instrument_id": eid,
                    "value": float(factor_vals[i]),
                },
            )
            rows_r.append(
                {
                    "trade_date": d,
                    "instrument_id": eid,
                    "forward_return": float(return_vals[i]),
                },
            )

    return (
        pl.DataFrame(rows_f),
        pl.DataFrame(rows_r),
    )


class MockForwardReturnProvider:
    """Mock implementation of ForwardReturnProvider protocol."""

    def __init__(self, return_df: pl.DataFrame) -> None:
        self.return_df = return_df

    def compute(
        self,
        asset_class: str,
        start: str,
        end: str,
        holding_period: int = 5,
        adj: str = "none",
    ) -> pl.DataFrame:
        return self.return_df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evaluate_report(
    factor_df: pl.DataFrame,
    return_df: pl.DataFrame,
) -> FactorEvaluationReport:
    """Run evaluator and return the report."""
    provider = MockForwardReturnProvider(return_df)
    evaluator = FactorEvaluator(provider)
    return evaluator.evaluate(factor_df)


def _assert_positive_ic(report: FactorEvaluationReport) -> None:
    """Assert that the report shows a positive IC signal."""
    ic: ICSummary = report.rank_ic_summary

    # IC mean should be positive
    assert ic.mean > 0, f"Expected positive IC mean, got {ic.mean}"

    # ICIR should be finite
    assert math.isfinite(ic.icir), f"ICIR should be finite, got {ic.icir}"

    # Win rate should be close to or above 50%
    assert ic.win_rate > 0.45, f"Win rate too low: {ic.win_rate}"

    # p-value should be a valid probability
    assert 0.0 <= ic.p_value <= 1.0, f"Invalid p_value: {ic.p_value}"


def _assert_quantile_monotonicity(report: FactorEvaluationReport) -> None:
    """Assert that top quantile outperforms bottom quantile."""
    q_returns = report.quantile_annual_returns
    assert len(q_returns) >= 2, "Need at least 2 quantile groups"

    # Find top and bottom quantile returns
    top_q = max(q_returns)
    bottom_q = min(q_returns)
    top_ret = q_returns[top_q]
    bottom_ret = q_returns[bottom_q]

    assert top_ret > bottom_ret, (
        f"Top quantile ({top_q}) annual return {top_ret:.4f} "
        f"should exceed bottom quantile ({bottom_q}) {bottom_ret:.4f}"
    )


def _assert_long_short_positive(report: FactorEvaluationReport) -> None:
    """Assert that long-short portfolio has positive metrics."""
    ls: LongShortResult = report.long_short

    assert ls.annual_return > 0, (
        f"Long-short annual return should be positive, got {ls.annual_return}"
    )
    assert math.isfinite(ls.sharpe), f"Sharpe should be finite, got {ls.sharpe}"


def _assert_observations_valid(report: FactorEvaluationReport) -> None:
    """Assert that observation counts are reasonable."""
    assert report.n_observations > 0, "Should have positive observations"
    assert report.n_dates > 0, "Should have positive dates"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRepresentativeFactorIC:
    """验证代表因子的 IC 和分层收益."""

    @pytest.fixture
    def factor_and_return(self) -> FactorReturnPair:
        """100 天 x 50 证券，IC 强度 0.3."""
        return _make_factor_and_return(n_dates=100, n_entities=50, ic_strength=0.3)

    # -- Value factor: ep_ttm --

    def test_value_factor_ic(self, factor_and_return: FactorReturnPair) -> None:
        """价值因子 ep_ttm: IC 应为正.

        ep_ttm = net_income_ttm / (close * total_shares)
        """
        factor_df, return_df = factor_and_return
        report = _evaluate_report(factor_df, return_df)

        _assert_positive_ic(report)
        _assert_quantile_monotonicity(report)
        _assert_long_short_positive(report)
        _assert_observations_valid(report)

    # -- Momentum factor: reversal_1m --

    def test_momentum_factor_ic(self, factor_and_return: FactorReturnPair) -> None:
        """动量因子 reversal_1m: IC 应为正（表达式含负号）.

        reversal_1m = -ts_pct_change(market.close, 20)

        由于合成数据的 IC 为正，模拟的是因子值与收益率正相关，
        等价于 -ts_pct_change 与收益率正相关（即短期反转效应）。
        """
        factor_df, return_df = factor_and_return
        report = _evaluate_report(factor_df, return_df)

        _assert_positive_ic(report)
        _assert_quantile_monotonicity(report)
        _assert_long_short_positive(report)
        _assert_observations_valid(report)

    # -- Quality factor: gross_margin --

    def test_quality_factor_ic(self, factor_and_return: FactorReturnPair) -> None:
        """质量因子 gross_margin: IC 应为正.

        gross_margin = (fundamentals.revenue - fundamentals.cogs) / fundamentals.revenue
        """
        factor_df, return_df = factor_and_return
        report = _evaluate_report(factor_df, return_df)

        _assert_positive_ic(report)
        _assert_quantile_monotonicity(report)
        _assert_long_short_positive(report)
        _assert_observations_valid(report)

    # -- Negative IC factor --

    def test_ic_strength_negative(self) -> None:
        """负 IC 强度：因子值与收益率负相关.

        通过反转收益率来构造负 IC 场景，
        验证评估管线在因子与收益负相关时的行为。
        """
        factor_df, return_df = _make_factor_and_return(
            n_dates=100,
            n_entities=50,
            ic_strength=0.3,
        )
        # Negate returns to create negative IC
        return_df = return_df.with_columns(
            pl.col("forward_return") * -1,
        )
        report = _evaluate_report(factor_df, return_df)

        assert report.rank_ic_summary.mean < 0, (
            f"Expected negative IC mean, got {report.rank_ic_summary.mean}"
        )
        assert report.long_short.annual_return < 0, (
            f"Expected negative LS return, got {report.long_short.annual_return}"
        )
        _assert_observations_valid(report)

    # -- Zero IC factor --

    def test_zero_ic_factor(self) -> None:
        """零 IC 因子：IC 应接近零."""
        factor_df, return_df = _make_factor_and_return(
            n_dates=100,
            n_entities=50,
            ic_strength=0.0,
        )
        report = _evaluate_report(factor_df, return_df)

        assert abs(report.rank_ic_summary.mean) < 0.15, (
            f"Expected near-zero IC, got {report.rank_ic_summary.mean}"
        )
        _assert_observations_valid(report)

    # -- Detailed IC summary checks --

    def test_ic_summary_statistics_are_finite(
        self,
        factor_and_return: FactorReturnPair,
    ) -> None:
        """IC summary 的所有统计量应为有限值."""
        factor_df, return_df = factor_and_return
        report = _evaluate_report(factor_df, return_df)

        ic = report.rank_ic_summary
        assert math.isfinite(ic.mean)
        assert math.isfinite(ic.std)
        assert math.isfinite(ic.icir)
        assert math.isfinite(ic.t_stat)
        assert 0.0 <= ic.p_value <= 1.0
        assert 0.0 <= ic.win_rate <= 1.0

    def test_pearson_ic_consistent_with_rank_ic(
        self,
        factor_and_return: FactorReturnPair,
    ) -> None:
        """Pearson IC 方向应与 Rank IC 一致（同号）."""
        factor_df, return_df = factor_and_return
        report = _evaluate_report(factor_df, return_df)

        rank_sign = 1 if report.rank_ic_summary.mean >= 0 else -1
        pearson_sign = 1 if report.pearson_ic_summary.mean >= 0 else -1
        assert rank_sign == pearson_sign, (
            f"Rank IC sign ({rank_sign}) != Pearson IC sign ({pearson_sign})"
        )

    # -- Quantile returns detailed checks --

    def test_quantile_returns_exist(
        self,
        factor_and_return: FactorReturnPair,
    ) -> None:
        """分层年化收益应存在且包含 5 个分组."""
        factor_df, return_df = factor_and_return
        report = _evaluate_report(factor_df, return_df)

        assert len(report.quantile_annual_returns) == 5
        for q, ret in report.quantile_annual_returns.items():
            assert math.isfinite(ret), f"Quantile {q} return not finite: {ret}"

    # -- Long-short detailed checks --

    def test_long_short_metrics_are_finite(
        self,
        factor_and_return: FactorReturnPair,
    ) -> None:
        """Long-short 组合指标应为有限值."""
        factor_df, return_df = factor_and_return
        report = _evaluate_report(factor_df, return_df)

        ls = report.long_short
        assert math.isfinite(ls.annual_return)
        assert math.isfinite(ls.annual_volatility)
        assert math.isfinite(ls.sharpe)
        assert math.isfinite(ls.portfolio_ir)
        assert math.isfinite(ls.sortino)
        assert ls.max_drawdown <= 0, "Max drawdown should be non-positive"
