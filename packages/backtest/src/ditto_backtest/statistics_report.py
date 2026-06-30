"""
回测报告构建 — build_report 组合所有统计维度.

提供 build_report 公共函数。
"""

from __future__ import annotations

from ditto_kernel import traced

from ditto_backtest._statistics_types import BacktestReport
from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.statistics_alpha import compute_alpha_statistics
from ditto_backtest.statistics_returns import compute_portfolio_statistics
from ditto_backtest.statistics_trades import (
    compute_aggregated_trade_statistics,
    compute_trade_statistics,
)

__all__ = ["build_report"]


@traced("backtest.statistics.report")
def build_report(
    collector: ExecutionAuditCollector,
    run_id: str = "",
    benchmark_navs: tuple[float, ...] | None = None,
) -> BacktestReport:
    """
    构建完整回测报告.

    Args:
        collector: 审计数据收集器。
        run_id: 回测运行 ID。
        benchmark_navs: 可选基准 NAV 序列。

    Returns:
        BacktestReport 实例。

    """
    portfolio_stats = compute_portfolio_statistics(collector)
    trade_stats = compute_trade_statistics(collector)
    aggregated_stats = compute_aggregated_trade_statistics(collector)
    alpha_stats = compute_alpha_statistics(collector, benchmark_navs)

    snapshots = collector.get_daily_snapshots()

    # NAV series
    nav_series = tuple((date, view.nav) for date, view in snapshots)

    # Period
    if portfolio_stats:
        start_date = portfolio_stats[0].trade_date
        end_date = portfolio_stats[-1].trade_date
    else:
        start_date = ""
        end_date = ""

    initial_cash = snapshots[0][1].nav if snapshots else 0.0
    final_nav = snapshots[-1][1].nav if snapshots else 0.0
    final_account_state = snapshots[-1][1] if snapshots else None

    closed_trades = collector.get_closed_trades()
    fills = collector.get_fills()

    return BacktestReport(
        run_id=run_id,
        period=(start_date, end_date),
        initial_cash=initial_cash,
        final_nav=final_nav,
        trade_stats=trade_stats,
        portfolio_stats=portfolio_stats,
        aggregated_trade_stats=aggregated_stats,
        alpha_stats=alpha_stats,
        nav_series=nav_series,
        trade_log=tuple(closed_trades),
        fill_log=tuple(fills),
        risk_log=collector.get_risk_log(),
        pre_trade_log=collector.get_pre_trade_log(),
        final_account_state=final_account_state,
    )
