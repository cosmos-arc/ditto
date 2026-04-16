"""
comparison_math — 回测 vs 实际对比的纯计算函数.

提供 ComparisonMetrics 数据类和 compute_comparison_from_raw 及其依赖的
数学辅助函数，不含任何 I/O 操作或门面编排逻辑。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ditto_kernel.math import pearson_correlation

from ditto_app.config import DEFAULT_INITIAL_CASH
from ditto_app.execution_dto import ManualExecutionFill
from ditto_app.query._artifact_utils import compute_total_return

__all__ = [
    "ComparisonMetrics",
    "compute_comparison_from_raw",
]

_TRADING_DAYS_PER_YEAR = 252
_MIN_PAIRED_POINTS = 2
_MIN_POINTS_FOR_TRACKING_ERROR = 3
_BPS_FACTOR = 10_000.0


@dataclass(frozen=True)
class ComparisonMetrics:
    """
    回测 vs 实际对比指标.

    Attributes:
        backtest_return: 回测年化收益率 (%)
        actual_return: 实际总收益率 (%)
        return_diff: 收益率偏差 (actual - backtest) (%)
        return_diff_bps: 基点偏差
        backtest_sharpe: 回测 Sharpe
        actual_sharpe: 实际 Sharpe
        backtest_total_cost: 回测总成本
        actual_total_cost: 实际总成本
        cost_drag_bps: 成本拖累 (基点)
        nav_correlation: NAV 序列 Pearson 相关系数
        max_nav_diff_bps: 最大 NAV 偏差 (基点)
        avg_daily_tracking_error_bps: 日均跟踪误差 (基点)

    """

    backtest_return: float
    actual_return: float | None  # 实验性: 无真实 NAV 时为 None
    return_diff: float | None
    return_diff_bps: float | None
    backtest_sharpe: float
    actual_sharpe: float
    backtest_total_cost: float
    actual_total_cost: float
    cost_drag_bps: float
    nav_correlation: float
    max_nav_diff_bps: float
    avg_daily_tracking_error_bps: float


def compute_comparison_from_raw(
    backtest_return: float,
    backtest_sharpe: float,
    backtest_total_cost: float,
    backtest_nav_series: list[tuple[str, float]],
    actual_fills: list[ManualExecutionFill],
    actual_navs: list[tuple[str, float]],
    initial_cash: float = DEFAULT_INITIAL_CASH,
) -> ComparisonMetrics:
    """
    从原始指标计算回测 vs 实际对比.

    Args:
        backtest_return: 回测年化收益率 (%).
        backtest_sharpe: 回测 Sharpe 比率.
        backtest_total_cost: 回测总手续费.
        backtest_nav_series: 回测 NAV 序列 [(date, nav), ...].
        actual_fills: 实际成交记录列表.
        actual_navs: 实际 NAV 序列 [(date, nav), ...].
        initial_cash: 初始资金（用于基点计算）.

    Returns:
        ComparisonMetrics 实例.

    """
    actual_return = _compute_total_return(actual_navs)
    actual_sharpe = _compute_sharpe_from_navs(actual_navs)
    actual_total_cost = sum(f.fee for f in actual_fills)

    return_diff: float | None = (
        actual_return - backtest_return if actual_return is not None else None
    )
    return_diff_bps: float | None = (
        return_diff * 100.0 if return_diff is not None else None
    )

    cost_drag_bps = (
        (actual_total_cost - backtest_total_cost) / initial_cash * _BPS_FACTOR
        if initial_cash > 0
        else 0.0
    )

    bt_navs = tuple(backtest_nav_series)
    nav_correlation = _compute_nav_correlation(bt_navs, actual_navs)
    max_nav_diff_bps = _compute_max_nav_diff_bps(bt_navs, actual_navs, initial_cash)
    avg_daily_tracking_error_bps = _compute_tracking_error_bps(bt_navs, actual_navs)

    return ComparisonMetrics(
        backtest_return=backtest_return,
        actual_return=actual_return,
        return_diff=return_diff,
        return_diff_bps=return_diff_bps,
        backtest_sharpe=backtest_sharpe,
        actual_sharpe=actual_sharpe,
        backtest_total_cost=backtest_total_cost,
        actual_total_cost=actual_total_cost,
        cost_drag_bps=cost_drag_bps,
        nav_correlation=nav_correlation,
        max_nav_diff_bps=max_nav_diff_bps,
        avg_daily_tracking_error_bps=avg_daily_tracking_error_bps,
    )


# ------------------------------------------------------------------
# 内部计算辅助
# ------------------------------------------------------------------


def _compute_total_return(navs: list[tuple[str, float]]) -> float | None:
    """从 NAV 序列计算总收益率 (%). 无足够数据时返回 None."""
    if len(navs) < _MIN_PAIRED_POINTS:
        return None
    initial = navs[0][1]
    final = navs[-1][1]
    if initial == 0:
        return None
    return compute_total_return(initial_cash=initial, final_nav=final) * 100.0


def _compute_sharpe_from_navs(navs: list[tuple[str, float]]) -> float:
    """从 NAV 序列计算 Sharpe 比率 (假设无风险利率为 0)."""
    if len(navs) < _MIN_PAIRED_POINTS:
        return 0.0
    nav_values = [v for _, v in navs]
    daily_returns = _daily_returns(nav_values)

    # 二次检查: _daily_returns 可能返回空列表（如连续相同 NAV）
    n = len(daily_returns)
    if n < _MIN_PAIRED_POINTS:
        return 0.0

    mean_ret = sum(daily_returns) / n
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (n - 1)
    if variance == 0:
        return 0.0

    ann_vol = math.sqrt(variance) * math.sqrt(_TRADING_DAYS_PER_YEAR)
    ann_ret = mean_ret * _TRADING_DAYS_PER_YEAR
    return ann_ret / ann_vol if ann_vol > 0 else 0.0


def _align_nav_series(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
    min_points: int = _MIN_PAIRED_POINTS,
) -> tuple[list[float], list[float]]:
    """
    对齐两条 NAV 序列到共同日期，返回 (bt_values, actual_values).

    Returns:
        空列表对齐时 (空, 空)；不足 min_points 时 (空, 空).

    """
    if not bt_navs or not actual_navs:
        return [], []

    bt_dict = dict(bt_navs)
    actual_dict = dict(actual_navs)
    common_dates = sorted(set(bt_dict.keys()) & set(actual_dict.keys()))

    if len(common_dates) < min_points:
        return [], []

    return (
        [bt_dict[d] for d in common_dates],
        [actual_dict[d] for d in common_dates],
    )


def _compute_nav_correlation(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
) -> float:
    """计算两条 NAV 序列的 Pearson 相关系数."""
    bt_values, actual_values = _align_nav_series(bt_navs, actual_navs)
    if not bt_values:
        return 0.0
    return pearson_correlation(bt_values, actual_values)


def _compute_max_nav_diff_bps(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
    initial_cash: float,
) -> float:
    """计算最大 NAV 偏差 (基点)."""
    if initial_cash <= 0:
        return 0.0

    bt_values, actual_values = _align_nav_series(
        bt_navs,
        actual_navs,
        min_points=1,
    )
    if not bt_values:
        return 0.0

    max_diff_bps = 0.0
    for bt_v, actual_v in zip(bt_values, actual_values, strict=True):
        diff = abs(bt_v - actual_v)
        bps = diff / initial_cash * _BPS_FACTOR
        max_diff_bps = max(max_diff_bps, bps)

    return max_diff_bps


def _compute_tracking_error_bps(
    bt_navs: tuple[tuple[str, float], ...],
    actual_navs: list[tuple[str, float]],
) -> float:
    """计算日均跟踪误差 (基点)."""
    bt_values, actual_values = _align_nav_series(
        bt_navs,
        actual_navs,
        min_points=_MIN_POINTS_FOR_TRACKING_ERROR,
    )
    if not bt_values:
        return 0.0

    bt_returns = _daily_returns(bt_values)
    actual_returns = _daily_returns(actual_values)

    if not bt_returns or not actual_returns:
        return 0.0

    min_len = min(len(bt_returns), len(actual_returns))
    if min_len < _MIN_PAIRED_POINTS:
        return 0.0

    excess = [bt_returns[i] - actual_returns[i] for i in range(min_len)]

    mean_excess = sum(excess) / min_len
    te_var = sum((e - mean_excess) ** 2 for e in excess) / (min_len - 1)
    if te_var <= 0:
        return 0.0

    # 日均超额收益标准差 → 基点 (CFA Institute 标准)
    return math.sqrt(te_var) * _BPS_FACTOR


def _daily_returns(navs: list[float]) -> list[float]:
    """将 NAV 序列转为日收益率序列 (小数)."""
    result: list[float] = []
    for i in range(1, len(navs)):
        if navs[i - 1] != 0:
            result.append(navs[i] / navs[i - 1] - 1)
        else:
            result.append(0.0)
    return result
