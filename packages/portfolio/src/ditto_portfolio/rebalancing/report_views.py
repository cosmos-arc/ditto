"""
Portfolio boundary types — decoupled from backtest module.

Defines the minimal interface that the portfolio comparison logic requires
from a backtest report, allowing portfolio to depend only on its own
boundary types rather than on ditto_backtest.statistics.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["AggregatedTradeStatsView", "AlphaStatsView", "BacktestReportView"]


@runtime_checkable
class AlphaStatsView(Protocol):
    """Minimal interface for alpha statistics consumed by comparison logic."""

    @property
    def annualized_return(self) -> float: ...
    @property
    def sharpe_ratio(self) -> float: ...
    @property
    def sortino_ratio(self) -> float: ...
    @property
    def max_drawdown(self) -> float: ...
    @property
    def total_turnover(self) -> float: ...
    @property
    def total_fees(self) -> float: ...
    @property
    def cost_drag(self) -> float: ...


@runtime_checkable
class AggregatedTradeStatsView(Protocol):
    """Aggregated trade stats consumed by comparison logic."""

    @property
    def total_trades(self) -> int: ...


@runtime_checkable
class BacktestReportView(Protocol):
    """
    Minimal interface for a backtest report consumed by comparison logic.

    ``ditto_backtest.statistics.BacktestReport`` satisfies this protocol
    without any changes.
    """

    @property
    def run_id(self) -> str: ...

    @property
    def final_nav(self) -> float: ...

    @property
    def alpha_stats(self) -> AlphaStatsView: ...

    @property
    def aggregated_trade_stats(self) -> AggregatedTradeStatsView: ...
