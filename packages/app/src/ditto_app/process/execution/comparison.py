"""
ComparisonReport — 回测 vs 实际对比计算（BacktestReport 版）.

提供 compute_comparison 函数，从 BacktestReport 对象计算对比指标。
"""

from __future__ import annotations

from ditto_engine.backtest.statistics import BacktestReport

from ditto_app.config import DEFAULT_INITIAL_CASH
from ditto_app.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
)
from ditto_app.query.comparison import ComparisonMetrics, compute_comparison_from_raw

__all__ = ["compute_comparison"]


def compute_comparison(
    backtest_report: BacktestReport,
    actual_snapshots: list[ActualPositionSnapshot],
    actual_fills: list[ManualExecutionFill],
    actual_navs: list[tuple[str, float]],
    initial_cash: float = DEFAULT_INITIAL_CASH,
) -> ComparisonMetrics:
    """
    计算回测 vs 实际对比指标.

    Args:
        backtest_report: 回测报告（含 alpha_stats, nav_series）.
        actual_snapshots: 实际持仓快照列表.
        actual_fills: 实际成交记录列表.
        actual_navs: 实际 NAV 序列 [(date, nav), ...].
        initial_cash: 初始资金（用于基点计算）.

    Returns:
        ComparisonMetrics 实例.

    """
    alpha = backtest_report.alpha_stats
    bt_nav_series = [(str(d), v) for d, v in backtest_report.nav_series]

    return compute_comparison_from_raw(
        backtest_return=alpha.annualized_return,
        backtest_sharpe=alpha.sharpe_ratio,
        backtest_total_cost=alpha.total_fees,
        backtest_nav_series=bt_nav_series,
        actual_fills=actual_fills,
        actual_navs=actual_navs,
        initial_cash=initial_cash,
    )
