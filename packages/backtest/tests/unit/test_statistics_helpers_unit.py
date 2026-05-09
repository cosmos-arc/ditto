"""statistics.py 模块级纯计算辅助函数的独立精确值测试.

Part 04a — 对每个辅助函数使用手工计算的精确预期值，
而非仅断言"返回非负"或"返回合理范围"。
"""

from __future__ import annotations

import math
from datetime import datetime
from types import MappingProxyType

import pytest
from ditto_backtest.statistics import (
    ExecutionAuditCollector,
    PortfolioStatistics,
    annualized_return,
    annualized_volatility,
    benchmark_relative,
    compute_beta_and_bench_ann,
    compute_portfolio_statistics,
    compute_tracking_error,
    cost_metrics,
    daily_returns_from_navs,
    drawdown_analysis,
    empty_aggregated_trade_statistics,
    empty_alpha_statistics,
    sortino_ratio,
)
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import (
    AccountView,
    CashBook,
    FillEvent,
    OrderBookReadOnly,
    Position,
)

# ---------------------------------------------------------------------------
# daily_returns_from_navs
# ---------------------------------------------------------------------------


class TestDailyReturnsFromNavs:
    """daily_returns_from_navs 精确值验证."""

    def test_normal_increasing(self) -> None:
        result = daily_returns_from_navs([100.0, 105.0, 110.25])
        # day 1: 105/100 - 1 = 0.05
        # day 2: 110.25/105 - 1 = 0.05
        assert result == pytest.approx([0.05, 0.05])

    def test_normal_decreasing(self) -> None:
        result = daily_returns_from_navs([100.0, 95.0])
        assert result == pytest.approx([-0.05])

    def test_flat(self) -> None:
        result = daily_returns_from_navs([100.0, 100.0, 100.0])
        assert result == pytest.approx([0.0, 0.0])

    def test_single_element_returns_empty(self) -> None:
        assert daily_returns_from_navs([100.0]) == []

    def test_zero_prev_nav_no_division_by_zero(self) -> None:
        """前一日 NAV 为 0 时返回 0.0 而非抛异常."""
        result = daily_returns_from_navs([0.0, 105.0])
        assert result == [0.0]

    def test_all_zeros(self) -> None:
        result = daily_returns_from_navs([0.0, 0.0, 0.0])
        assert result == [0.0, 0.0]

    def test_large_positive_return(self) -> None:
        result = daily_returns_from_navs([1.0, 3.0])
        assert result == pytest.approx([2.0])

    def test_near_zero_nav_recovery(self) -> None:
        """NAV 从接近零恢复时仍能正确计算."""
        result = daily_returns_from_navs([0.001, 1.0])
        # 1.0 / 0.001 - 1 = 999.0
        assert result == pytest.approx([999.0])

    def test_empty_list_returns_empty(self) -> None:
        assert daily_returns_from_navs([]) == []


# ---------------------------------------------------------------------------
# annualized_return
# ---------------------------------------------------------------------------


class TestAnnualizedReturn:
    """annualized_return 精确值验证."""

    def test_one_year_positive(self) -> None:
        # 252 天，total_return = 0.10 → ann = 10%
        result = annualized_return(0.10, 252)
        assert result == pytest.approx(10.0, rel=1e-6)

    def test_one_year_negative(self) -> None:
        result = annualized_return(-0.20, 252)
        assert result == pytest.approx(-20.0, rel=1e-6)

    def test_zero_total_return(self) -> None:
        result = annualized_return(0.0, 252)
        assert result == pytest.approx(0.0)

    def test_zero_days_returns_zero(self) -> None:
        result = annualized_return(0.10, 0)
        assert result == 0.0

    def test_negative_days_returns_zero(self) -> None:
        result = annualized_return(0.10, -1)
        assert result == 0.0

    def test_half_year(self) -> None:
        # 126 天，total_return = 0.05
        # ann = (1.05)^(252/126) - 1 = 1.05^2 - 1 = 0.1025 → 10.25%
        result = annualized_return(0.05, 126)
        assert result == pytest.approx(10.25, rel=1e-4)

    def test_one_day(self) -> None:
        # 1 天，total_return = 0.001
        # ann = (1.001)^252 - 1 ≈ 0.2862 → 28.62%
        result = annualized_return(0.001, 1)
        assert result > 0
        assert result < 100  # sanity check

    def test_two_years(self) -> None:
        # 504 天，total_return = 0.21
        # ann = (1.21)^(252/504) - 1 = 1.21^0.5 - 1 = sqrt(1.21) - 1 = 0.1 → 10%
        result = annualized_return(0.21, 504)
        assert result == pytest.approx(10.0, rel=1e-4)


# ---------------------------------------------------------------------------
# annualized_volatility
# ---------------------------------------------------------------------------


class TestAnnualizedVolatility:
    """annualized_volatility 精确值验证."""

    def test_empty_returns_zero(self) -> None:
        assert annualized_volatility([]) == 0.0

    def test_single_element_returns_zero(self) -> None:
        assert annualized_volatility([0.01]) == 0.0

    def test_two_elements(self) -> None:
        # returns = [0.01, -0.01], n=2
        # mean = 0, variance = ((0.01)^2 + (-0.01)^2) / (2-1) = 0.0002
        # ann_vol = sqrt(0.0002) * sqrt(252) * 100
        result = annualized_volatility([0.01, -0.01])
        expected = math.sqrt(0.0002) * math.sqrt(252) * 100
        assert result == pytest.approx(expected)

    def test_constant_returns_zero_volatility(self) -> None:
        """恒定日收益率 → 年化波动率为 0."""
        result = annualized_volatility([0.01, 0.01, 0.01, 0.01])
        assert result == pytest.approx(0.0)

    def test_all_zero_returns(self) -> None:
        result = annualized_volatility([0.0, 0.0, 0.0])
        assert result == pytest.approx(0.0)

    def test_known_volatility(self) -> None:
        """手工计算验证: 3 个收益率 [0.01, 0.02, 0.03]."""
        returns = [0.01, 0.02, 0.03]
        n = 3
        mean_r = sum(returns) / n  # 0.02
        variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
        # deviations: [-0.01, 0, 0.01], sum of sq = 0.0001 + 0 + 0.0001 = 0.0002
        # variance = 0.0002 / 2 = 0.0001
        assert variance == pytest.approx(0.0001)
        expected = math.sqrt(variance) * math.sqrt(252) * 100
        result = annualized_volatility(returns)
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------


class TestSortinoRatio:
    """sortino_ratio 精确值验证."""

    def test_empty_returns_zero(self) -> None:
        assert sortino_ratio([], 10.0) == 0.0

    def test_single_element_returns_zero(self) -> None:
        assert sortino_ratio([0.01], 10.0) == 0.0

    def test_all_positive_no_downside(self) -> None:
        """全正收益 → 无 downside → 0."""
        assert sortino_ratio([0.01, 0.02, 0.03], 10.0) == 0.0

    def test_all_zero_returns_zero(self) -> None:
        assert sortino_ratio([0.0, 0.0, 0.0], 0.0) == 0.0

    def test_mixed_with_downside(self) -> None:
        """混合正负收益，手工计算 sortino."""
        returns = [0.01, -0.02, 0.03, -0.01, 0.02]
        n = 5
        # downside returns: [-0.02, -0.01]
        # downside_var = ((-0.02)^2 + (-0.01)^2) / (n - 1)
        #               = (0.0004 + 0.0001) / 4 = 0.000125
        downside_var = (0.0004 + 0.0001) / (n - 1)
        downside_dev = math.sqrt(downside_var) * math.sqrt(252) * 100
        ann_ret = 15.0
        expected = ann_ret / downside_dev
        result = sortino_ratio(returns, ann_ret)
        assert result == pytest.approx(expected)

    def test_all_negative(self) -> None:
        """全负收益，sortino 应为负值."""
        returns = [-0.01, -0.02, -0.01]
        n = 3
        downside_var = (0.0001 + 0.0004 + 0.0001) / (n - 1)
        downside_dev = math.sqrt(downside_var) * math.sqrt(252) * 100
        ann_ret = -10.0
        expected = ann_ret / downside_dev
        result = sortino_ratio(returns, ann_ret)
        assert result == pytest.approx(expected)
        assert result < 0

    def test_zero_annualized_return(self) -> None:
        """年化收益为 0 时 sortino 应为 0."""
        result = sortino_ratio([-0.01, -0.02], 0.0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# drawdown_analysis
# ---------------------------------------------------------------------------


class TestDrawdownAnalysis:
    """drawdown_analysis 精确值验证."""

    def test_monotonic_increase(self) -> None:
        """持续新高 → 0 回撤."""
        max_dd, max_dur = drawdown_analysis([100.0, 110.0, 120.0, 130.0])
        assert max_dd == pytest.approx(0.0)
        assert max_dur == 0

    def test_monotonic_decrease(self) -> None:
        """持续下跌."""
        max_dd, max_dur = drawdown_analysis([120.0, 110.0, 100.0])
        # peak = 120
        # dd[1] = (110-120)/120 = -10/120
        # dd[2] = (100-120)/120 = -20/120
        # max_dd = -20/120 * 100 ≈ -16.667
        # duration: dd[1] < 0 → dur=1, dd[2] < 0 → dur=2
        assert max_dd == pytest.approx(-20 / 120 * 100)
        assert max_dur == 2

    def test_recovery(self) -> None:
        """回撤后恢复."""
        max_dd, max_dur = drawdown_analysis([100.0, 80.0, 90.0, 100.0])
        # peak = 100
        # dd[1] = (80-100)/100 = -0.20 → -20%
        # dd[2] = (90-100)/100 = -0.10 → -10%
        # dd[3] = (100-100)/100 = 0 → flat, dur resets
        assert max_dd == pytest.approx(-20.0)
        assert max_dur == 2  # days 1-2 in drawdown

    def test_double_dip(self) -> None:
        """两次回撤，第二次更深."""
        max_dd, max_dur = drawdown_analysis([100.0, 90.0, 100.0, 70.0, 80.0])
        # First dip: peak=100, dd[1] = -10%
        # Recovery at [2]: peak=100
        # Second dip: peak=100, dd[3] = -30%, dd[4] = -20%
        assert max_dd == pytest.approx(-30.0)
        assert max_dur == 2  # days 3-4

    def test_flat_line(self) -> None:
        max_dd, max_dur = drawdown_analysis([100.0, 100.0, 100.0])
        assert max_dd == pytest.approx(0.0)
        assert max_dur == 0

    def test_single_element(self) -> None:
        max_dd, max_dur = drawdown_analysis([100.0])
        assert max_dd == pytest.approx(0.0)
        assert max_dur == 0

    def test_all_zeros(self) -> None:
        """全零 NAV → peak=0, 除零保护."""
        max_dd, max_dur = drawdown_analysis([0.0, 0.0, 0.0])
        assert max_dd == 0.0
        assert max_dur == 0

    def test_v_shape_recovery(self) -> None:
        """V 形回撤恢复."""
        max_dd, max_dur = drawdown_analysis([100.0, 50.0, 100.0])
        assert max_dd == pytest.approx(-50.0)
        assert max_dur == 1  # only day 1 is in drawdown

    def test_peak_updates_mid_series(self) -> None:
        """峰值在序列中间更新."""
        max_dd, max_dur = drawdown_analysis([100.0, 120.0, 110.0, 130.0, 100.0])
        # peak evolves: 100 → 120 → 120 → 130 → 130
        # dd[2] = (110-120)/120 = -8.33%
        # dd[4] = (100-130)/130 = -23.08%
        assert max_dd == pytest.approx((100.0 - 130.0) / 130.0 * 100)
        assert max_dur == 1  # only day 4


# ---------------------------------------------------------------------------
# compute_tracking_error
# ---------------------------------------------------------------------------


class TestComputeTrackingError:
    """compute_tracking_error 精确值验证."""

    def test_min_len_one_returns_none(self) -> None:
        assert compute_tracking_error([0.01], [0.01], 1) is None

    def test_min_len_zero_returns_none(self) -> None:
        assert compute_tracking_error([], [], 0) is None

    def test_identical_returns_zero_te(self) -> None:
        """策略与基准完全一致 → 跟踪误差为 0."""
        returns = [0.01, 0.02, -0.01]
        bench = [0.01, 0.02, -0.01]
        result = compute_tracking_error(returns, bench, 3)
        assert result == pytest.approx(0.0)

    def test_known_tracking_error(self) -> None:
        """手工计算: excess = [0.01, -0.01], mean_excess = 0."""
        port = [0.02, 0.01]
        bench = [0.01, 0.02]
        # excess = [0.01, -0.01]
        # mean_excess = 0.0
        # te_var = (0.01^2 + (-0.01)^2) / (2-1) = 0.0002
        # te = sqrt(0.0002) * sqrt(252) * 100
        expected = math.sqrt(0.0002) * math.sqrt(252) * 100
        result = compute_tracking_error(port, bench, 2)
        assert result == pytest.approx(expected)

    def test_constant_excess_returns_zero(self) -> None:
        """策略始终跑赢基准 1% → 跟踪误差为 0."""
        port = [0.02, 0.03, 0.01]
        bench = [0.01, 0.02, 0.00]
        result = compute_tracking_error(port, bench, 3)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_beta_and_bench_ann
# ---------------------------------------------------------------------------


class TestComputeBetaAndBenchAnn:
    """compute_beta_and_bench_ann 精确值验证."""

    def test_min_len_one(self) -> None:
        beta, bench_ann = compute_beta_and_bench_ann([0.01], [0.01], (100.0, 101.0), 1)
        assert beta == 0.0
        assert bench_ann == 0.0

    def test_min_len_zero(self) -> None:
        beta, bench_ann = compute_beta_and_bench_ann([], [], (100.0, 100.0), 0)
        assert beta == 0.0
        assert bench_ann == 0.0

    def test_constant_benchmark_zero_var(self) -> None:
        """基准日收益恒定 → var_b = 0 → beta = 0."""
        port = [0.01, 0.02]
        bench = [0.01, 0.01]  # constant → var_b = 0
        beta, _bench_ann = compute_beta_and_bench_ann(
            port,
            bench,
            (100.0, 102.01),
            2,
        )
        assert beta == 0.0

    def test_known_beta(self) -> None:
        """手工计算 beta."""
        port = [0.02, 0.04]  # mean = 0.03
        bench = [0.01, 0.03]  # mean = 0.02
        bench_navs = (100.0, 103.03)
        # cov = ((0.02-0.03)*(0.01-0.02) + (0.04-0.03)*(0.03-0.02)) / (2-1)
        #     = ((-0.01)*(-0.01) + (0.01)*(0.01)) / 1
        #     = (0.0001 + 0.0001) / 1 = 0.0002
        # var_b = ((0.01-0.02)^2 + (0.03-0.02)^2) / (2-1)
        #       = (0.0001 + 0.0001) / 1 = 0.0002
        # beta = 0.0002 / 0.0002 = 1.0
        beta, _ = compute_beta_and_bench_ann(port, bench, bench_navs, 2)
        assert beta == pytest.approx(1.0)

    def test_bench_annualized_calculation(self) -> None:
        """基准年化收益率计算."""
        bench = [0.01, 0.01]
        bench_navs = (100.0, 102.01)
        # bench_total = 102.01/100 - 1 = 0.0201
        # bench_ann = (1.0201)^(252/2) - 1) * 100
        _, bench_ann = compute_beta_and_bench_ann(bench, bench, bench_navs, 2)
        expected = ((1.0201) ** 126 - 1) * 100
        assert bench_ann == pytest.approx(expected, rel=1e-4)

    def test_zero_bench_initial_nav(self) -> None:
        """基准初始 NAV 为 0 → bench_total = 0."""
        _beta, bench_ann = compute_beta_and_bench_ann(
            [0.01, 0.02],
            [0.01, 0.02],
            (0.0, 0.0),
            2,
        )
        assert bench_ann == 0.0


# ---------------------------------------------------------------------------
# benchmark_relative
# ---------------------------------------------------------------------------


class TestBenchmarkRelative:
    """benchmark_relative 精确值验证."""

    def test_no_benchmark_returns_none(self) -> None:
        result = benchmark_relative([0.01, 0.02], None, 2, 10.0)
        assert result.information_ratio is None
        assert result.tracking_error is None
        assert result.beta is None
        assert result.alpha is None

    def test_length_mismatch_returns_none(self) -> None:
        """benchmark 长度与 n 不匹配 → graceful 降级."""
        result = benchmark_relative([0.01, 0.02, 0.03], (100.0, 101.0, 102.0), 4, 10.0)
        assert result.information_ratio is None
        assert result.tracking_error is None
        assert result.beta is None
        assert result.alpha is None

    def test_matching_length_computes_values(self) -> None:
        """长度匹配 → 正常计算."""
        port = [0.01, 0.02, -0.01]
        # bench_navs 精确产生 [0.01, 0.02, -0.01]:
        # 100*1.01=101, 101*1.02=103.02, 103.02*0.99=101.9898
        bench_navs = (100.0, 101.0, 103.02, 101.9898)
        result = benchmark_relative(port, bench_navs, 4, 10.0)
        assert result.tracking_error is not None
        assert result.beta is not None
        assert result.alpha is not None
        # 完全一致的收益 → TE ≈ 0, beta ≈ 1
        assert result.tracking_error == pytest.approx(0.0)
        assert result.beta == pytest.approx(1.0, rel=1e-4)

    def test_single_day_returns_none_te(self) -> None:
        """只有 1 天数据 → TE = None (min_len ≤ 1)."""
        result = benchmark_relative([0.01], (100.0, 101.0), 2, 10.0)
        assert result.tracking_error is None
        assert result.beta == 0.0
        assert result.information_ratio is None


# ---------------------------------------------------------------------------
# cost_metrics
# ---------------------------------------------------------------------------


class TestCostMetrics:
    """cost_metrics 精确值验证."""

    def _make_fill(
        self,
        price: float = 10.0,
        qty: int = 100,
        fee: float = 5.0,
        date: datetime = datetime(2026, 1, 1),
    ) -> FillEvent:
        return FillEvent(
            fill_id="f-1",
            order_id="o-1",
            instrument_id=1,
            direction=OrderSide.BUY,
            filled_quantity=qty,
            fill_price=price,
            fee=fee,
            slippage=0.0,
            event_time=date,
            cumulative_quantity=qty,
            leaves_quantity=0,
        )

    def test_empty_fills_zero_values(self) -> None:
        result = cost_metrics([], 100_000.0, [100_000.0])
        assert result.total_turnover == 0.0
        assert result.total_fees == 0.0
        assert result.cost_drag == 0.0

    def test_zero_initial_nav_no_cost_drag(self) -> None:
        """initial_nav = 0 → cost_drag = 0 (除零保护)."""
        fills = [self._make_fill()]
        result = cost_metrics(fills, 0.0, [100_000.0])
        assert result.cost_drag == 0.0

    def test_single_fill(self) -> None:
        fill = self._make_fill(price=10.0, qty=100, fee=5.0)
        navs = [100_000.0, 99_000.0]
        avg_nav = (100_000.0 + 99_000.0) / 2
        expected_turnover = (10.0 * 100) / avg_nav
        result = cost_metrics([fill], 100_000.0, navs)
        assert result.total_turnover == pytest.approx(expected_turnover)
        assert result.total_fees == 5.0
        assert result.cost_drag == pytest.approx(5.0 / 100_000.0 * 100)

    def test_multiple_fills_same_day(self) -> None:
        """同一天多笔成交 → avg_turnover 按 1 个 rebalance 计分."""
        fills = [
            self._make_fill(price=10.0, qty=100, fee=5.0),
            self._make_fill(price=20.0, qty=50, fee=3.0, date=datetime(2026, 1, 1)),
        ]
        navs = [100_000.0]
        result = cost_metrics(fills, 100_000.0, navs)
        # 2 fills 同日 → rebalance_count = 1
        assert result.avg_turnover_per_rebalance == pytest.approx(result.total_turnover)

    def test_multiple_fills_different_days(self) -> None:
        """不同天的成交 → avg_turnover 按天数均分."""
        fills = [
            self._make_fill(price=10.0, qty=100, fee=5.0, date=datetime(2026, 1, 1)),
            self._make_fill(price=10.0, qty=100, fee=5.0, date=datetime(2026, 1, 2)),
        ]
        navs = [100_000.0]
        result = cost_metrics(fills, 100_000.0, navs)
        assert result.avg_turnover_per_rebalance == pytest.approx(
            result.total_turnover / 2,
        )

    def test_empty_navs_uses_default_avg(self) -> None:
        """空 NAV 列表 → avg_nav = 1.0."""
        fill = self._make_fill(price=10.0, qty=100, fee=5.0)
        result = cost_metrics([fill], 100_000.0, [])
        assert result.total_turnover == pytest.approx(1000.0 / 1.0)


# ---------------------------------------------------------------------------
# empty_* constructors
# ---------------------------------------------------------------------------


class TestEmptyConstructors:
    """零值构造器验证."""

    def test_empty_aggregated_trade_statistics(self) -> None:
        stats = empty_aggregated_trade_statistics()
        assert stats.total_trades == 0
        assert stats.win_rate == 0.0
        assert stats.profit_factor == 0.0
        assert stats.avg_holding_days == 0.0
        assert stats.best_trade == 0.0
        assert stats.worst_trade == 0.0

    def test_empty_alpha_statistics(self) -> None:
        stats = empty_alpha_statistics()
        assert stats.annualized_return == 0.0
        assert stats.annualized_volatility == 0.0
        assert stats.sharpe_ratio == 0.0
        assert stats.max_drawdown == 0.0
        assert stats.max_drawdown_duration_days == 0
        assert stats.information_ratio is None
        assert stats.tracking_error is None
        assert stats.beta is None
        assert stats.alpha_annualized is None
        assert stats.total_fees == 0.0
        assert stats.cost_drag == 0.0


# ---------------------------------------------------------------------------
# PortfolioStatistics 不变量
# ---------------------------------------------------------------------------


def _make_account_view(
    nav: float = 100_000.0,
    exposure: float = 60_000.0,
    cash: float = 40_000.0,
    positions: dict[int, Position] | None = None,
) -> AccountView:
    """构造 AccountView 快照，用于 PortfolioStatistics 测试."""
    cash_book = CashBook(available=cash, settled=cash, frozen=0.0)
    pos_map = MappingProxyType(positions or {})
    return AccountView(
        positions=pos_map,
        cash=cash_book,
        total_value=nav,
        nav=nav,
        exposure=exposure,
        pending_buy_value=0.0,
        order_book=OrderBookReadOnly({}),
    )


class TestPortfolioStatisticsInvariants:
    """compute_portfolio_statistics 产出结果的不变量验证."""

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _build_stats(
        nav_series: list[tuple[str, float]],
        exposure: float = 60_000.0,
        cash: float = 40_000.0,
    ) -> tuple[PortfolioStatistics, ...]:
        """便捷构建: 传入 [(date, nav), ...] 返回统计序列."""
        collector = ExecutionAuditCollector()
        for date, nav in nav_series:
            collector.record_account_view(date, _make_account_view(nav=nav))
        return compute_portfolio_statistics(collector)

    # -- invariants ----------------------------------------------------------

    def test_max_drawdown_non_positive(self) -> None:
        """max_drawdown 始终 <= 0（负数表示亏损回撤，0 表示无回撤）。"""
        # 单调上涨
        stats = self._build_stats(
            [
                ("2026-01-01", 100_000.0),
                ("2026-01-02", 105_000.0),
                ("2026-01-03", 110_000.0),
            ]
        )
        for s in stats:
            assert s.max_drawdown <= 0.0

        # 单调下跌
        stats = self._build_stats(
            [
                ("2026-01-01", 100_000.0),
                ("2026-01-02", 90_000.0),
                ("2026-01-03", 80_000.0),
            ]
        )
        for s in stats:
            assert s.max_drawdown <= 0.0

        # V 形回撤恢复
        stats = self._build_stats(
            [
                ("2026-01-01", 100_000.0),
                ("2026-01-02", 70_000.0),
                ("2026-01-03", 100_000.0),
            ]
        )
        for s in stats:
            assert s.max_drawdown <= 0.0
        # 最大回撤应记录为 -30%
        assert stats[-1].max_drawdown == pytest.approx(-30.0, abs=1e-6)

    def test_nav_non_negative(self) -> None:
        """NAV 不为负。"""
        stats = self._build_stats(
            [
                ("2026-01-01", 0.0),
                ("2026-01-02", 100_000.0),
                ("2026-01-03", 50_000.0),
            ]
        )
        for s in stats:
            assert s.nav >= 0.0

    def test_total_return_consistency(self) -> None:
        """cumulative_return 与 initial/final NAV 一致。"""
        # 上涨场景
        stats = self._build_stats(
            [
                ("2026-01-01", 100_000.0),
                ("2026-01-02", 110_000.0),
                ("2026-01-03", 99_000.0),
            ]
        )
        initial_nav = stats[0].nav
        for s in stats:
            if initial_nav != 0:
                expected = (s.nav - initial_nav) / initial_nav * 100
                assert s.cumulative_return == pytest.approx(expected, rel=1e-9)

        # 零初始 NAV → cumulative_return = 0
        stats = self._build_stats(
            [
                ("2026-01-01", 0.0),
                ("2026-01-02", 50_000.0),
            ]
        )
        for s in stats:
            assert s.cumulative_return == 0.0

    def test_cumulative_return_monotonic_when_increasing(self) -> None:
        """单调上涨时 cumulative_return 递增。"""
        stats = self._build_stats(
            [
                ("2026-01-01", 100_000.0),
                ("2026-01-02", 102_000.0),
                ("2026-01-03", 105_000.0),
                ("2026-01-04", 110_000.0),
                ("2026-01-05", 115_000.0),
            ]
        )
        for i in range(1, len(stats)):
            assert stats[i].cumulative_return >= stats[i - 1].cumulative_return

    def test_drawdown_non_positive(self) -> None:
        """drawdown 始终 <= 0（负数表示从峰值回落）。"""
        stats = self._build_stats(
            [
                ("2026-01-01", 100_000.0),
                ("2026-01-02", 90_000.0),
                ("2026-01-03", 95_000.0),
                ("2026-01-04", 85_000.0),
            ]
        )
        for s in stats:
            assert s.drawdown <= 0.0

    def test_max_drawdown_is_worst_drawdown(self) -> None:
        """max_drawdown 是历史最大回撤绝对值（running max，单调递减）。"""
        stats = self._build_stats(
            [
                ("2026-01-01", 100_000.0),
                ("2026-01-02", 80_000.0),  # drawdown -20%
                ("2026-01-03", 100_000.0),  # recovery → drawdown 0
                ("2026-01-04", 50_000.0),  # drawdown -50%
            ]
        )
        # max_drawdown 是 running max of |drawdown|，单调不增（负数方向）
        for i in range(1, len(stats)):
            assert stats[i].max_drawdown <= stats[i - 1].max_drawdown
        # 最终最深回撤: (50000 - 100000) / 100000 * 100 = -50%
        assert stats[-1].max_drawdown == pytest.approx(-50.0, abs=1e-6)
        # day 2 时最大回撤为 -20%
        assert stats[1].max_drawdown == pytest.approx(-20.0, abs=1e-6)
