"""
Alpha/基准统计计算 — 跟踪误差、Beta、信息比率、成本分析.

提供 compute_alpha_statistics 公共函数及内部基准辅助函数。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ditto_kernel import traced

from ditto_backtest._statistics_types import AlphaStatistics
from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.statistics_returns import (
    TRADING_DAYS_PER_YEAR,
    annualized_return,
    annualized_volatility,
    daily_returns_from_navs,
    drawdown_analysis,
    safe_ratio,
    sortino_ratio,
    total_return,
)
from ditto_backtest.statistics_trades import cost_metrics

__all__ = [
    "benchmark_relative",
    "compute_alpha_statistics",
    "compute_beta_and_bench_ann",
    "compute_tracking_error",
    "empty_alpha_statistics",
]


@dataclass(frozen=True)
class BenchmarkRelative:
    """Benchmark-relative statistics."""

    information_ratio: float | None
    tracking_error: float | None
    beta: float | None
    alpha: float | None


@traced("backtest.statistics.alpha")
def compute_alpha_statistics(
    collector: ExecutionAuditCollector,
    benchmark_navs: tuple[float, ...] | None = None,
) -> AlphaStatistics:
    """
    从 NAV 序列计算绩效分析统计.

    Args:
        collector: 审计数据收集器。
        benchmark_navs: 可选的基准 NAV 序列（长度须与快照一致）。

    Returns:
        AlphaStatistics 实例。

    """
    snapshots = collector.get_daily_snapshots()
    fills = collector.get_fills()
    navs = [view.nav for _, view in snapshots]

    if not navs:
        return empty_alpha_statistics()

    n = len(navs)
    initial_nav = navs[0]
    daily_returns = daily_returns_from_navs(navs)
    total_days = len(daily_returns)
    total_ret = total_return(navs)

    ann_ret = annualized_return(total_ret, total_days)
    ann_vol = annualized_volatility(daily_returns)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    sortino = sortino_ratio(daily_returns, ann_ret)
    max_dd, max_dd_dur = drawdown_analysis(navs)
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0.0

    bench_rel = benchmark_relative(
        daily_returns,
        benchmark_navs,
        n,
        ann_ret,
    )

    cost = cost_metrics(list(fills), initial_nav, navs)

    net_return_after_cost = total_ret * 100 - cost.cost_drag

    return AlphaStatistics(
        annualized_return=ann_ret,
        annualized_volatility=ann_vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_dd,
        max_drawdown_duration_days=max_dd_dur,
        calmar_ratio=calmar,
        information_ratio=bench_rel.information_ratio,
        tracking_error=bench_rel.tracking_error,
        beta=bench_rel.beta,
        alpha_annualized=bench_rel.alpha,
        total_turnover=cost.total_turnover,
        avg_turnover_per_rebalance=cost.avg_turnover_per_rebalance,
        total_fees=cost.total_fees,
        net_return_after_cost=net_return_after_cost,
        cost_drag=cost.cost_drag,
    )


def benchmark_relative(
    daily_returns: list[float],
    benchmark_navs: tuple[float, ...] | None,
    n: int,
    ann_return: float,
) -> BenchmarkRelative:
    """Compute benchmark-relative statistics."""
    if benchmark_navs is None or len(benchmark_navs) != n:
        return BenchmarkRelative(None, None, None, None)

    bench_returns = daily_returns_from_navs(list(benchmark_navs))
    min_len = min(len(daily_returns), len(bench_returns))

    tracking_error_val = compute_tracking_error(daily_returns, bench_returns, min_len)
    beta_val, bench_annualized = compute_beta_and_bench_ann(
        daily_returns,
        bench_returns,
        benchmark_navs,
        min_len,
    )

    ir = None
    if tracking_error_val is not None and tracking_error_val > 0:
        ir = (ann_return - bench_annualized) / tracking_error_val

    alpha_val = ann_return - beta_val * bench_annualized

    return BenchmarkRelative(ir, tracking_error_val, beta_val, alpha_val)


def compute_tracking_error(
    daily_returns: list[float],
    bench_returns: list[float],
    min_len: int,
) -> float | None:
    """Compute annualized tracking error (%)."""
    if min_len <= 1:
        return None
    excess = [daily_returns[i] - bench_returns[i] for i in range(min_len)]
    mean_excess = sum(excess) / min_len
    te_var = sum((e - mean_excess) ** 2 for e in excess) / (min_len - 1)
    return math.sqrt(te_var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100


def compute_beta_and_bench_ann(
    daily_returns: list[float],
    bench_returns: list[float],
    benchmark_navs: tuple[float, ...],
    min_len: int,
) -> tuple[float, float]:
    """Compute beta and benchmark annualized return (%)."""
    if min_len <= 1:
        return 0.0, 0.0

    mean_p = sum(daily_returns[:min_len]) / min_len
    mean_b = sum(bench_returns[:min_len]) / min_len
    cov = sum(
        (daily_returns[i] - mean_p) * (bench_returns[i] - mean_b)
        for i in range(min_len)
    ) / (min_len - 1)
    var_b = sum((bench_returns[i] - mean_b) ** 2 for i in range(min_len)) / (
        min_len - 1
    )
    beta = safe_ratio(cov, var_b)

    bench_total = total_return(list(benchmark_navs))
    bench_annualized = (
        (1 + bench_total) ** (TRADING_DAYS_PER_YEAR / max(min_len, 1)) - 1
    ) * 100

    return beta, bench_annualized


def empty_alpha_statistics() -> AlphaStatistics:
    """Return AlphaStatistics with numeric fields zeroed, benchmark fields None."""
    return AlphaStatistics(
        annualized_return=0.0,
        annualized_volatility=0.0,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        max_drawdown=0.0,
        max_drawdown_duration_days=0,
        calmar_ratio=0.0,
        information_ratio=None,
        tracking_error=None,
        beta=None,
        alpha_annualized=None,
        total_turnover=0.0,
        avg_turnover_per_rebalance=0.0,
        total_fees=0.0,
        net_return_after_cost=0.0,
        cost_drag=0.0,
    )
