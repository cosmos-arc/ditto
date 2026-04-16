"""comparison_math.py 纯计算函数单元测试."""

from __future__ import annotations

import pytest
from ditto_app.execution_dto import ManualExecutionFill
from ditto_app.query.comparison_math import (
    ComparisonMetrics,
    _align_nav_series,
    _compute_max_nav_diff_bps,
    _compute_nav_correlation,
    _compute_sharpe_from_navs,
    _compute_total_return,
    _compute_tracking_error_bps,
    _daily_returns,
    compute_comparison_from_raw,
)

# ------------------------------------------------------------------
# Helper: 构造 ManualExecutionFill（非 dataclass，需用 __init__）
# ------------------------------------------------------------------


def _make_fill(fee: float = 0.0) -> ManualExecutionFill:
    """构造一个只填必要字段的 ManualExecutionFill 实例."""
    return ManualExecutionFill(
        fill_id="test-fill",
        intent_id="test-intent",
        strategy_id="test-strategy",
        trade_date="2026-01-02",
        instrument_id=510050,
        direction="buy",
        quantity=1000,
        fill_price=3.0,
        fee=fee,
    )


# ==================================================================
# _compute_total_return
# ==================================================================


class TestComputeTotalReturn:
    """_compute_total_return 测试."""

    def test_normal_case(self) -> None:
        """正常 NAV 序列返回正确的总收益率 (%)."""
        navs = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 110.0),
            ("2026-01-03", 121.0),
        ]
        result = _compute_total_return(navs)
        assert result == pytest.approx(21.0)

    def test_initial_zero_returns_none(self) -> None:
        """初始 NAV 为 0 时返回 None."""
        navs = [
            ("2026-01-01", 0.0),
            ("2026-01-02", 100.0),
        ]
        result = _compute_total_return(navs)
        assert result is None

    def test_single_value_returns_none(self) -> None:
        """仅一个 NAV 点时返回 None（不足 _MIN_PAIRED_POINTS）."""
        navs = [("2026-01-01", 100.0)]
        result = _compute_total_return(navs)
        assert result is None

    def test_empty_returns_none(self) -> None:
        """空 NAV 序列返回 None."""
        result = _compute_total_return([])
        assert result is None

    def test_loss_case(self) -> None:
        """NAV 下跌时返回负收益率."""
        navs = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 90.0),
        ]
        result = _compute_total_return(navs)
        assert result == pytest.approx(-10.0)


# ==================================================================
# _compute_sharpe_from_navs
# ==================================================================


class TestComputeSharpeFromNavs:
    """_compute_sharpe_from_navs 测试."""

    def test_normal_case(self) -> None:
        """正常 NAV 序列返回合理的 Sharpe 比率."""
        # 构造一个趋势向上的 NAV 序列
        navs = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
            ("2026-01-03", 102.0),
            ("2026-01-04", 103.5),
            ("2026-01-05", 105.0),
        ]
        result = _compute_sharpe_from_navs(navs)
        # 持续上涨序列 Sharpe 应为正
        assert result > 0.0

    def test_variance_zero_returns_zero(self) -> None:
        """所有 NAV 完全相同时返回 0.0（零方差）."""
        navs = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 100.0),
            ("2026-01-03", 100.0),
        ]
        result = _compute_sharpe_from_navs(navs)
        assert result == 0.0

    def test_empty_list_returns_zero(self) -> None:
        """空 NAV 序列返回 0.0."""
        result = _compute_sharpe_from_navs([])
        assert result == 0.0

    def test_single_element_returns_zero(self) -> None:
        """单元素 NAV 序列返回 0.0（不足 _MIN_PAIRED_POINTS）."""
        navs = [("2026-01-01", 100.0)]
        result = _compute_sharpe_from_navs(navs)
        assert result == 0.0

    def test_two_elements_returns_zero(self) -> None:
        """两个元素时 _daily_returns 只有 1 个值，不足 n-1 除法需要，返回 0.0."""
        navs = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 110.0),
        ]
        result = _compute_sharpe_from_navs(navs)
        assert result == 0.0


# ==================================================================
# _daily_returns
# ==================================================================


class TestDailyReturns:
    """_daily_returns 测试."""

    def test_normal_case(self) -> None:
        """正常 NAV 序列计算日收益率."""
        navs = [100.0, 110.0, 99.0]
        result = _daily_returns(navs)
        assert len(result) == 2
        assert result[0] == pytest.approx(0.10)
        assert result[1] == pytest.approx(-0.10)

    def test_previous_zero_defensive(self) -> None:
        """前一日 NAV 为 0 时返回 0.0（防御分支）."""
        navs = [0.0, 100.0, 110.0]
        result = _daily_returns(navs)
        assert result[0] == 0.0
        assert result[1] == pytest.approx(0.10)

    def test_empty_list(self) -> None:
        """空列表返回空结果."""
        result = _daily_returns([])
        assert result == []

    def test_single_value(self) -> None:
        """单值列表返回空结果（无前值可除）."""
        result = _daily_returns([100.0])
        assert result == []


# ==================================================================
# _align_nav_series
# ==================================================================


class TestAlignNavSeries:
    """_align_nav_series 测试."""

    def test_normal_alignment(self) -> None:
        """正常序列对齐到共同日期."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
            ("2026-01-03", 102.0),
        )
        actual = [
            ("2026-01-01", 100.5),
            ("2026-01-02", 101.5),
            ("2026-01-03", 102.5),
        ]
        bt_vals, actual_vals = _align_nav_series(bt, actual)
        assert bt_vals == [100.0, 101.0, 102.0]
        assert actual_vals == [100.5, 101.5, 102.5]

    def test_empty_bt_returns_empty(self) -> None:
        """空回测 NAV 序列返回空."""
        _, actual_vals = _align_nav_series((), [("2026-01-01", 100.0)])
        assert actual_vals == []

    def test_empty_actual_returns_empty(self) -> None:
        """空实际 NAV 序列返回空."""
        bt_vals, _ = _align_nav_series((("2026-01-01", 100.0),), [])
        assert bt_vals == []

    def test_no_common_dates_returns_empty(self) -> None:
        """无共同日期返回空."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
        )
        actual = [
            ("2026-01-03", 102.0),
            ("2026-01-04", 103.0),
        ]
        bt_vals, actual_vals = _align_nav_series(bt, actual)
        assert bt_vals == []
        assert actual_vals == []

    def test_partial_overlap(self) -> None:
        """部分重叠日期仅保留共同部分."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
            ("2026-01-03", 102.0),
        )
        actual = [
            ("2026-01-02", 101.5),
            ("2026-01-03", 102.5),
            ("2026-01-04", 103.5),
        ]
        bt_vals, actual_vals = _align_nav_series(bt, actual)
        assert bt_vals == [101.0, 102.0]
        assert actual_vals == [101.5, 102.5]


# ==================================================================
# _compute_nav_correlation
# ==================================================================


class TestComputeNavCorrelation:
    """_compute_nav_correlation 测试."""

    def test_normal_correlation(self) -> None:
        """正常序列返回合理的相关系数."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
            ("2026-01-03", 102.0),
            ("2026-01-04", 103.0),
        )
        actual = [
            ("2026-01-01", 100.5),
            ("2026-01-02", 101.5),
            ("2026-01-03", 102.5),
            ("2026-01-04", 103.5),
        ]
        result = _compute_nav_correlation(bt, actual)
        # 完美线性相关应为 1.0
        assert result == pytest.approx(1.0)

    def test_perfect_correlation(self) -> None:
        """完全相同的两条序列相关系数为 1.0."""
        navs = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 105.0),
            ("2026-01-03", 110.0),
        )
        result = _compute_nav_correlation(navs, list(navs))
        assert result == pytest.approx(1.0)

    def test_no_common_dates_returns_zero(self) -> None:
        """无共同日期返回 0.0."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
        )
        actual = [
            ("2026-01-03", 102.0),
            ("2026-01-04", 103.0),
        ]
        result = _compute_nav_correlation(bt, actual)
        assert result == 0.0

    def test_min_paired_points_insufficient(self) -> None:
        """共同日期不足 _MIN_PAIRED_POINTS 返回 0.0."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
        )
        actual = [
            ("2026-01-01", 100.5),
        ]
        result = _compute_nav_correlation(bt, actual)
        assert result == 0.0


# ==================================================================
# _compute_max_nav_diff_bps
# ==================================================================


class TestComputeMaxNavDiffBps:
    """_compute_max_nav_diff_bps 测试."""

    def test_normal_diff(self) -> None:
        """正常序列计算最大 NAV 偏差（基点）."""
        bt = (
            ("2026-01-01", 1_000_000.0),
            ("2026-01-02", 1_010_000.0),
        )
        actual = [
            ("2026-01-01", 1_000_100.0),
            ("2026-01-02", 1_009_000.0),
        ]
        # 日期1: diff=100, bps=100/1e6*10000=1.0
        # 日期2: diff=1000, bps=1000/1e6*10000=10.0
        result = _compute_max_nav_diff_bps(bt, actual, initial_cash=1_000_000.0)
        assert result == pytest.approx(10.0)

    def test_empty_input_returns_zero(self) -> None:
        """空输入返回 0.0."""
        result = _compute_max_nav_diff_bps((), [], initial_cash=1_000_000.0)
        assert result == 0.0

    def test_zero_initial_cash_returns_zero(self) -> None:
        """initial_cash <= 0 时返回 0.0."""
        bt = (("2026-01-01", 100.0),)
        actual = [("2026-01-01", 200.0)]
        result = _compute_max_nav_diff_bps(bt, actual, initial_cash=0.0)
        assert result == 0.0


# ==================================================================
# _compute_tracking_error_bps
# ==================================================================


class TestComputeTrackingErrorBps:
    """_compute_tracking_error_bps 测试."""

    def test_normal_case(self) -> None:
        """正常序列返回非零跟踪误差."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
            ("2026-01-03", 102.0),
            ("2026-01-04", 103.0),
        )
        actual = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.5),
            ("2026-01-03", 102.2),
            ("2026-01-04", 103.8),
        ]
        result = _compute_tracking_error_bps(bt, actual)
        # 跟踪误差应为正数
        assert result > 0.0

    def test_insufficient_points_returns_zero(self) -> None:
        """共同日期不足 _MIN_POINTS_FOR_TRACKING_ERROR (3) 返回 0.0."""
        bt = (
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
        )
        actual = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
        ]
        result = _compute_tracking_error_bps(bt, actual)
        assert result == 0.0

    def test_perfect_tracking_returns_zero(self) -> None:
        """完美跟踪（两条序列完全相同）返回 0.0（te_var <= 0）."""
        navs = [
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
            ("2026-01-03", 102.0),
            ("2026-01-04", 103.0),
        ]
        result = _compute_tracking_error_bps(tuple(navs), navs)
        assert result == 0.0


# ==================================================================
# compute_comparison_from_raw
# ==================================================================


class TestComputeComparisonFromRaw:
    """compute_comparison_from_raw 集成测试."""

    def test_normal_path(self) -> None:
        """正常输入返回完整 ComparisonMetrics."""
        bt_navs = [
            ("2026-01-01", 1_000_000.0),
            ("2026-01-02", 1_005_000.0),
            ("2026-01-03", 1_010_000.0),
            ("2026-01-04", 1_015_000.0),
            ("2026-01-05", 1_020_000.0),
        ]
        actual_navs = [
            ("2026-01-01", 1_000_000.0),
            ("2026-01-02", 1_004_000.0),
            ("2026-01-03", 1_009_000.0),
            ("2026-01-04", 1_014_500.0),
            ("2026-01-05", 1_019_000.0),
        ]
        fills = [_make_fill(fee=50.0), _make_fill(fee=30.0)]

        result = compute_comparison_from_raw(
            backtest_return=5.0,
            backtest_sharpe=1.5,
            backtest_total_cost=60.0,
            backtest_nav_series=bt_navs,
            actual_fills=fills,
            actual_navs=actual_navs,
            initial_cash=1_000_000.0,
        )

        assert isinstance(result, ComparisonMetrics)
        assert result.backtest_return == 5.0
        assert result.backtest_sharpe == 1.5
        assert result.backtest_total_cost == 60.0
        # actual_return: (1_019_000 - 1_000_000) / 1_000_000 * 100 = 1.9%
        assert result.actual_return == pytest.approx(1.9)
        # return_diff: 1.9 - 5.0 = -3.1
        assert result.return_diff == pytest.approx(-3.1)
        # return_diff_bps: -3.1 * 100 = -310.0
        assert result.return_diff_bps == pytest.approx(-310.0)
        # actual_total_cost: 50 + 30 = 80
        assert result.actual_total_cost == 80.0
        # cost_drag_bps: (80 - 60) / 1e6 * 10000 = 0.2
        assert result.cost_drag_bps == pytest.approx(0.2)
        # nav_correlation > 0 (趋势一致)
        assert result.nav_correlation > 0.0
        # max_nav_diff_bps > 0
        assert result.max_nav_diff_bps >= 0.0
        # avg_daily_tracking_error_bps >= 0
        assert result.avg_daily_tracking_error_bps >= 0.0

    def test_no_actual_navs(self) -> None:
        """无实际 NAV 时 actual_return / return_diff 为 None."""
        result = compute_comparison_from_raw(
            backtest_return=5.0,
            backtest_sharpe=1.5,
            backtest_total_cost=100.0,
            backtest_nav_series=[("2026-01-01", 1_000_000.0)],
            actual_fills=[],
            actual_navs=[],
            initial_cash=1_000_000.0,
        )
        assert result.actual_return is None
        assert result.return_diff is None
        assert result.return_diff_bps is None
