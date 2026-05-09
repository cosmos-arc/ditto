"""
交易统计计算 — 逐笔统计、汇总统计、成本指标.

提供 compute_trade_statistics / compute_aggregated_trade_statistics 公共函数。
"""

from __future__ import annotations

import statistics as stats_module
from dataclasses import dataclass

from ditto_portfolio.accounting import FillEvent

from ditto_backtest._statistics_types import AggregatedTradeStatistics, TradeStatistics
from ditto_backtest.audit import ExecutionAuditCollector

__all__ = [
    "compute_aggregated_trade_statistics",
    "compute_trade_statistics",
    "cost_metrics",
    "empty_aggregated_trade_statistics",
]


@dataclass(frozen=True)
class CostMetrics:
    """Turnover and fee metrics."""

    total_turnover: float
    avg_turnover_per_rebalance: float
    total_fees: float
    cost_drag: float


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
        return empty_aggregated_trade_statistics()

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
    median_hold = float(stats_module.median(holding_days))

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


def empty_aggregated_trade_statistics() -> AggregatedTradeStatistics:
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


def cost_metrics(
    fills: list[FillEvent],
    initial_nav: float,
    navs: list[float],
) -> CostMetrics:
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

    return CostMetrics(
        total_turnover=total_turnover,
        avg_turnover_per_rebalance=avg_turnover_per_rebalance,
        total_fees=total_fees,
        cost_drag=cost_drag,
    )
