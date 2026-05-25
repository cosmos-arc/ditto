"""
组合收益/波动率指标计算 — NAV 收益率、年化指标、回撤分析.

提供 compute_portfolio_statistics 公共函数及内部辅助函数。
"""

from __future__ import annotations

import math
from dataclasses import replace

from ditto_backtest._statistics_types import PortfolioStatistics
from ditto_backtest.audit import ExecutionAuditCollector

__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "annualized_return",
    "annualized_volatility",
    "compute_portfolio_statistics",
    "daily_returns_from_navs",
    "drawdown_analysis",
    "safe_ratio",
    "sortino_ratio",
    "total_return",
]

TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# 共享辅助函数（decimal 内部、调用方按需转 percentage）
# ---------------------------------------------------------------------------


def safe_ratio(numerator: float, denominator: float) -> float:
    """Guarded division: returns 0.0 when denominator is 0."""
    return numerator / denominator if denominator != 0 else 0.0


def total_return(navs: list[float]) -> float:
    """Compute total return from NAV series in decimal: navs[-1]/navs[0] - 1."""
    if not navs:
        return 0.0
    return safe_ratio(navs[-1], navs[0]) - (1.0 if navs[0] != 0 else 0.0)


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def compute_portfolio_statistics(
    collector: ExecutionAuditCollector,
) -> tuple[PortfolioStatistics, ...]:
    """
    从每日账户快照计算组合统计序列.

    Args:
        collector: 审计数据收集器。

    Returns:
        按 trade_date 排序的 PortfolioStatistics 元组。

    """
    snapshots = collector.get_daily_snapshots()
    stats: list[PortfolioStatistics] = []
    peak_nav = 0.0
    inception_nav: float | None = None

    for i, (date, view) in enumerate(snapshots):
        if inception_nav is None:
            inception_nav = view.nav

        # Daily return — reuse daily_returns_from_navs logic (decimal → * 100)
        if i > 0:
            prev_nav = snapshots[i - 1][1].nav
            daily_return = safe_ratio(view.nav - prev_nav, prev_nav) * 100
        else:
            daily_return = 0.0

        # Cumulative return — decimal → * 100
        cumulative_return = safe_ratio(view.nav - inception_nav, inception_nav) * 100

        # Drawdown — decimal → * 100
        peak_nav = max(peak_nav, view.nav)
        drawdown = safe_ratio(view.nav - peak_nav, peak_nav) * 100

        # Cash ratio
        cash_ratio = safe_ratio(view.cash.total, view.nav) * 100

        # Position count
        position_count = len(view.positions)

        stats.append(
            PortfolioStatistics(
                trade_date=date,
                nav=view.nav,
                daily_return=daily_return,
                cumulative_return=cumulative_return,
                drawdown=drawdown,
                max_drawdown=0.0,  # placeholder, second pass
                exposure=view.exposure,
                cash_ratio=cash_ratio,
                position_count=position_count,
            ),
        )

    # Second pass: running max of abs(drawdown) -> negative convention
    max_dd = 0.0
    final_stats: list[PortfolioStatistics] = []
    for s in stats:
        max_dd = max(max_dd, abs(s.drawdown))
        final_stats.append(replace(s, max_drawdown=-max_dd))

    return tuple(final_stats)


def daily_returns_from_navs(navs: list[float]) -> list[float]:
    """Convert NAV series to daily returns (decimal)."""
    result: list[float] = []
    for i in range(1, len(navs)):
        adjustment = 1.0 if navs[i - 1] != 0 else 0.0
        result.append(safe_ratio(navs[i], navs[i - 1]) - adjustment)
    return result


def annualized_return(total_return: float, total_days: int) -> float:
    """Compute annualized return (%). risk_free = 0."""
    if total_days <= 0:
        return 0.0
    ann = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / total_days) - 1
    return ann * 100


def annualized_volatility(
    daily_returns: list[float],
) -> float:
    """Compute annualized volatility (%)."""
    n = len(daily_returns)
    if n <= 1:
        return 0.0
    mean_ret = sum(daily_returns) / n
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (n - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100


def sortino_ratio(
    daily_returns: list[float],
    ann_return: float,
) -> float:
    """Compute Sortino ratio."""
    n = len(daily_returns)
    downside = [r for r in daily_returns if r < 0]
    if n <= 1 or not downside:
        return 0.0
    downside_var = sum(r**2 for r in downside) / (n - 1)
    downside_dev = math.sqrt(downside_var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100
    return ann_return / downside_dev if downside_dev > 0 else 0.0


def drawdown_analysis(
    navs: list[float],
) -> tuple[float, int]:
    """Compute max drawdown (%) and max drawdown duration (days)."""
    if not navs:
        return 0.0, 0

    max_dd = 0.0
    max_dd_dur = 0
    cur_dur = 0
    peak = navs[0]

    for nav in navs:
        if nav > peak:
            peak = nav
            cur_dur = 0
        else:
            dd = safe_ratio(nav - peak, peak)
            max_dd = min(max_dd, dd)
            if dd < 0:
                cur_dur += 1
                max_dd_dur = max(max_dd_dur, cur_dur)
            else:
                cur_dur = 0

    return max_dd * 100, max_dd_dur
