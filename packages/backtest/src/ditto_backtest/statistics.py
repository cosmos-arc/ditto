"""
统计计算 — 组合统计、交易统计、绩效分析、回测报告.

Facade: 从领域子模块 re-export 所有公共 API，保持对外接口不变。

子模块:
  - statistics_returns: 组合收益/波动率指标
  - statistics_trades: 交易统计与成本指标
  - statistics_alpha: Alpha/基准绩效指标
  - statistics_report: 报告构建
  - _statistics_types: frozen dataclass 类型定义

审计记录 (RiskScanRecord / PreTradeDecisionRecord) 和数据收集器
(ExecutionAuditCollector) 在 backtest.audit 子包中。
"""

from ditto_backtest._statistics_types import (
    AggregatedTradeStatistics,
    AlphaStatistics,
    BacktestReport,
    PortfolioStatistics,
    TradeStatistics,
)
from ditto_backtest.audit import (
    ExecutionAuditCollector,
    PreTradeDecisionRecord,
    RiskScanRecord,
)
from ditto_backtest.statistics_alpha import (
    benchmark_relative,
    compute_alpha_statistics,
    compute_beta_and_bench_ann,
    compute_tracking_error,
    empty_alpha_statistics,
)
from ditto_backtest.statistics_report import build_report
from ditto_backtest.statistics_returns import (
    annualized_return,
    annualized_volatility,
    compute_portfolio_statistics,
    daily_returns_from_navs,
    drawdown_analysis,
    sortino_ratio,
)
from ditto_backtest.statistics_trades import (
    compute_aggregated_trade_statistics,
    compute_trade_statistics,
    cost_metrics,
    empty_aggregated_trade_statistics,
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
    "annualized_return",
    "annualized_volatility",
    "benchmark_relative",
    "build_report",
    "compute_aggregated_trade_statistics",
    "compute_alpha_statistics",
    "compute_beta_and_bench_ann",
    "compute_portfolio_statistics",
    "compute_tracking_error",
    "compute_trade_statistics",
    "cost_metrics",
    "daily_returns_from_navs",
    "drawdown_analysis",
    "empty_aggregated_trade_statistics",
    "empty_alpha_statistics",
    "sortino_ratio",
]
