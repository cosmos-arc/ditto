"""
统计计算 — 组合统计、交易统计、绩效分析、回测报告.

提供 frozen statistics data classes 和模块级计算函数。
审计记录 (RiskScanRecord / PreTradeDecisionRecord) 和数据收集器
(ExecutionAuditCollector) 在 backtest.audit 子包中。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace

from ditto_portfolio.accounting.fills import FillEvent

from ditto_engine.backtest._statistics_types import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    PortfolioStatistics,
    TradeStatistics,
)
from ditto_engine.backtest.audit import (
    ExecutionAuditCollector,
    PreTradeDecisionRecord,
    RiskScanRecord,
)

__all__ = [
    "AggregatedTradeStatistics",
    "AlphaStatistics",
    "BacktestReport",
    "ExecutionAuditCollector",
    "PortfolioStatistics",
    "PreTradeDecisionRecord",
    "RiskScanRecord",
    "TradeStatistics",
    "build_report",
    "compute_aggregated_trade_statistics",
    "compute_alpha_statistics",
    "compute_portfolio_statistics",
    "compute_trade_statistics",
]

_TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Module-level computation functions
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

        # Daily return
        if i > 0:
            prev_nav = snapshots[i - 1][1].nav
            daily_return = (
                (view.nav - prev_nav) / prev_nav * 100 if prev_nav != 0 else 0.0
            )
        else:
            daily_return = 0.0

        # Cumulative return
        cumulative_return = (
            (view.nav - inception_nav) / inception_nav * 100
            if inception_nav != 0
            else 0.0
        )

        # Drawdown
        peak_nav = max(peak_nav, view.nav)
        drawdown = (view.nav - peak_nav) / peak_nav * 100 if peak_nav != 0 else 0.0

        # Cash ratio
        cash_ratio = view.cash.total / view.nav * 100 if view.nav != 0 else 0.0

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

    # Second pass: running max of abs(drawdown) → negative convention
    max_dd = 0.0
    final_stats: list[PortfolioStatistics] = []
    for s in stats:
        max_dd = max(max_dd, abs(s.drawdown))
        final_stats.append(replace(s, max_drawdown=-max_dd))

    return tuple(final_stats)


def compute_trade_statistics(
    collector: ExecutionAuditCollector,
) -> tuple[TradeStatistics, ...]:
    """
    将已记录的平仓交易转换为逐笔统计.

    Args:
        collector: 审计数据收集器。

    Returns:
        TradeStatistics 元组，每条对应一笔 TradeRecord。

    """
    closed_trades = collector.get_closed_trades()
    result: list[TradeStatistics] = []
    for trade in closed_trades:
        result.append(
            TradeStatistics(
                trade_id=trade.trade_id,
                instrument_id=trade.instrument_id,
                direction=trade.direction.value,
                entry_date=trade.entry_date,
                exit_date=trade.exit_date,
                holding_days=trade.holding_days,
                return_pct=trade.return_pct,
                gross_pnl=trade.gross_pnl,
                net_pnl=trade.net_pnl,
                fees=trade.fees,
            ),
        )
    return tuple(result)


def compute_aggregated_trade_statistics(
    collector: ExecutionAuditCollector,
) -> AggregatedTradeStatistics:
    """
    从已平仓交易计算汇总统计.

    仅统计 exit_date 非空的交易。
    无交易时所有数值字段返回 0.0。

    Args:
        collector: 审计数据收集器。

    Returns:
        AggregatedTradeStatistics 实例。

    """
    closed_trades = collector.get_closed_trades()

    # Filter closed trades only
    closed = [t for t in closed_trades if t.exit_date is not None]

    if not closed:
        return _empty_aggregated_trade_statistics()

    total = len(closed)
    longs = sum(1 for t in closed if t.direction.value == "buy")
    shorts = total - longs

    gross_pnls: list[float] = []
    return_pcts: list[float] = []
    holding_days: list[int] = []

    for t in closed:
        gp = t.gross_pnl if t.gross_pnl is not None else 0.0
        gross_pnls.append(gp)
        rp = t.return_pct if t.return_pct is not None else 0.0
        return_pcts.append(rp)
        hd = t.holding_days if t.holding_days is not None else 0
        holding_days.append(hd)

    wins = [g for g in gross_pnls if g > 0]
    losses = [g for g in gross_pnls if g < 0]
    win_count = len(wins)
    loss_count = len(losses)

    win_rate = win_count / total * 100 if total > 0 else 0.0
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = sum_wins / sum_losses if sum_losses > 0 else float("inf")

    avg_win = sum_wins / win_count if win_count > 0 else 0.0
    avg_loss = sum_losses / loss_count if loss_count > 0 else 0.0
    avg_win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

    # Consecutive wins/losses
    max_consec_wins = 0
    max_consec_losses = 0
    current_wins = 0
    current_losses = 0
    for g in gross_pnls:
        if g > 0:
            current_wins += 1
            current_losses = 0
        elif g < 0:
            current_losses += 1
            current_wins = 0
        else:
            current_wins = 0
            current_losses = 0
        max_consec_wins = max(max_consec_wins, current_wins)
        max_consec_losses = max(max_consec_losses, current_losses)

    avg_hold = sum(holding_days) / total
    median_hold = float(statistics.median(holding_days))

    best = max(gross_pnls)
    worst = min(gross_pnls)
    avg_ret = sum(return_pcts) / total

    return AggregatedTradeStatistics(
        total_trades=total,
        long_trades=longs,
        short_trades=shorts,
        win_trades=win_count,
        loss_trades=loss_count,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_win_loss_ratio=avg_win_loss_ratio,
        max_consecutive_wins=max_consec_wins,
        max_consecutive_losses=max_consec_losses,
        avg_holding_days=avg_hold,
        median_holding_days=median_hold,
        best_trade=best,
        worst_trade=worst,
        avg_trade_return_pct=avg_ret,
    )


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
        return _empty_alpha_statistics()

    n = len(navs)
    initial_nav = navs[0]
    daily_returns = _daily_returns_from_navs(navs)
    total_days = len(daily_returns)
    total_return = navs[-1] / initial_nav - 1 if initial_nav != 0 else 0.0

    ann_ret = _annualized_return(total_return, total_days)
    ann_vol = _annualized_volatility(daily_returns)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    sortino = _sortino_ratio(daily_returns, ann_ret)
    max_dd, max_dd_dur = _drawdown_analysis(navs)
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0.0

    bench_rel = _benchmark_relative(
        daily_returns,
        benchmark_navs,
        n,
        ann_ret,
    )

    cost = _cost_metrics(list(fills), initial_nav, navs)

    net_return_after_cost = total_return * 100 - cost.cost_drag

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
    )


# ---------------------------------------------------------------------------
# Module-level helper functions (pure computation)
# ---------------------------------------------------------------------------


def _daily_returns_from_navs(navs: list[float]) -> list[float]:
    """Convert NAV series to daily returns (decimal)."""
    result: list[float] = []
    for i in range(1, len(navs)):
        if navs[i - 1] != 0:
            result.append(navs[i] / navs[i - 1] - 1)
        else:
            result.append(0.0)
    return result


def _annualized_return(total_return: float, total_days: int) -> float:
    """Compute annualized return (%). risk_free = 0."""
    if total_days <= 0:
        return 0.0
    ann = (1 + total_return) ** (_TRADING_DAYS_PER_YEAR / total_days) - 1
    return ann * 100


def _annualized_volatility(
    daily_returns: list[float],
) -> float:
    """Compute annualized volatility (%)."""
    n = len(daily_returns)
    if n <= 1:
        return 0.0
    mean_ret = sum(daily_returns) / n
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (n - 1)
    return math.sqrt(variance) * math.sqrt(_TRADING_DAYS_PER_YEAR) * 100


def _sortino_ratio(
    daily_returns: list[float],
    ann_return: float,
) -> float:
    """Compute Sortino ratio."""
    n = len(daily_returns)
    downside = [r for r in daily_returns if r < 0]
    if n <= 1 or not downside:
        return 0.0
    downside_var = sum(r**2 for r in downside) / (n - 1)
    downside_dev = math.sqrt(downside_var) * math.sqrt(_TRADING_DAYS_PER_YEAR) * 100
    return ann_return / downside_dev if downside_dev > 0 else 0.0


def _drawdown_analysis(
    navs: list[float],
) -> tuple[float, int]:
    """Compute max drawdown (%) and max drawdown duration (days)."""
    max_dd = 0.0
    max_dd_dur = 0
    cur_dur = 0
    peak = navs[0]

    for nav in navs:
        if nav > peak:
            peak = nav
            cur_dur = 0
        else:
            dd = (nav - peak) / peak if peak != 0 else 0.0
            max_dd = min(max_dd, dd)
            if dd < 0:
                cur_dur += 1
                max_dd_dur = max(max_dd_dur, cur_dur)
            else:
                cur_dur = 0

    return max_dd * 100, max_dd_dur


@dataclass(frozen=True)
class _BenchmarkRelative:
    """Benchmark-relative statistics."""

    information_ratio: float | None
    tracking_error: float | None
    beta: float | None
    alpha: float | None


def _benchmark_relative(
    daily_returns: list[float],
    benchmark_navs: tuple[float, ...] | None,
    n: int,
    ann_return: float,
) -> _BenchmarkRelative:
    """Compute benchmark-relative statistics."""
    if benchmark_navs is None or len(benchmark_navs) != n:
        return _BenchmarkRelative(None, None, None, None)

    bench_returns = _daily_returns_from_navs(list(benchmark_navs))
    min_len = min(len(daily_returns), len(bench_returns))

    tracking_error_val = _compute_tracking_error(daily_returns, bench_returns, min_len)
    beta_val, bench_annualized = _compute_beta_and_bench_ann(
        daily_returns,
        bench_returns,
        benchmark_navs,
        min_len,
    )

    ir = None
    if tracking_error_val is not None and tracking_error_val > 0:
        ir = (ann_return - bench_annualized) / tracking_error_val

    alpha_val = ann_return - beta_val * bench_annualized

    return _BenchmarkRelative(ir, tracking_error_val, beta_val, alpha_val)


def _compute_tracking_error(
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
    return math.sqrt(te_var) * math.sqrt(_TRADING_DAYS_PER_YEAR) * 100


def _compute_beta_and_bench_ann(
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
    beta = cov / var_b if var_b > 0 else 0.0

    bench_initial = benchmark_navs[0]
    bench_total = benchmark_navs[-1] / bench_initial - 1 if bench_initial != 0 else 0.0
    bench_annualized = (
        (1 + bench_total) ** (_TRADING_DAYS_PER_YEAR / max(min_len, 1)) - 1
    ) * 100

    return beta, bench_annualized


@dataclass(frozen=True)
class _CostMetrics:
    """Turnover and fee metrics."""

    total_turnover: float
    avg_turnover_per_rebalance: float
    total_fees: float
    cost_drag: float


# ---------------------------------------------------------------------------
# Zero-value constructors for empty-case returns
# ---------------------------------------------------------------------------


def _empty_aggregated_trade_statistics() -> AggregatedTradeStatistics:
    """Return AggregatedTradeStatistics with all fields zeroed."""
    return AggregatedTradeStatistics(
        total_trades=0,
        long_trades=0,
        short_trades=0,
        win_trades=0,
        loss_trades=0,
        win_rate=0.0,
        profit_factor=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        avg_win_loss_ratio=0.0,
        max_consecutive_wins=0,
        max_consecutive_losses=0,
        avg_holding_days=0.0,
        median_holding_days=0.0,
        best_trade=0.0,
        worst_trade=0.0,
        avg_trade_return_pct=0.0,
    )


def _empty_alpha_statistics() -> AlphaStatistics:
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


def _cost_metrics(
    fills: list[FillEvent],
    initial_nav: float,
    navs: list[float],
) -> _CostMetrics:
    """Compute turnover and fee metrics."""
    n = len(navs)
    total_fill_value = sum(f.fill_price * f.filled_quantity for f in fills)
    avg_nav = sum(navs) / n if n > 0 else 1.0
    total_turnover = total_fill_value / avg_nav if avg_nav > 0 else 0.0

    days_with_fills: set[str] = set()
    for f in fills:
        days_with_fills.add(f.event_time.strftime("%Y-%m-%d"))
    rebalance_count = len(days_with_fills) if days_with_fills else 1
    avg_turnover_per_rebalance = total_turnover / rebalance_count

    total_fees = sum(f.fee for f in fills)
    cost_drag = total_fees / initial_nav * 100 if initial_nav > 0 else 0.0

    return _CostMetrics(
        total_turnover=total_turnover,
        avg_turnover_per_rebalance=avg_turnover_per_rebalance,
        total_fees=total_fees,
        cost_drag=cost_drag,
    )
