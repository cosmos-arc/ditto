"""
统计类型定义 — 从 statistics.py 提取的 frozen dataclasses.

提供 PortfolioStatistics / TradeStatistics / AggregatedTradeStatistics /
AlphaStatistics / BacktestReport 五个 frozen dataclass，
供 statistics.py 和其他模块导入使用。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_execution.trade_builder import TradeRecord
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.fills import FillEvent

from ditto_backtest.audit import (
    PreTradeDecisionRecord,
    RiskScanRecord,
)

__all__ = [
    "AggregatedTradeStatistics",
    "AlphaStatistics",
    "BacktestReport",
    "PortfolioStatistics",
    "TradeStatistics",
]


@dataclass(frozen=True)
class PortfolioStatistics:
    """
    每日组合级别统计 — 从 AccountView 快照序列计算得出.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        nav: 净值（总资产）
        daily_return: 日收益率 (%)，相对前一日
        cumulative_return: 累计收益率 (%)，相对起始日
        drawdown: 当前回撤 (%)，从峰值回落（负数）
        max_drawdown: 最大回撤 (%)，历史上最大回撤（负数）
        exposure: 持仓市值
        cash_ratio: 现金占比 (%)，cash / nav
        position_count: 持仓标的数量

    """

    trade_date: str
    nav: float
    daily_return: float
    cumulative_return: float
    drawdown: float
    max_drawdown: float
    exposure: float
    cash_ratio: float
    position_count: int


@dataclass(frozen=True)
class TradeStatistics:
    """
    逐笔交易统计 — 从 TradeRecord 映射得出.

    Attributes:
        trade_id: 交易 ID
        instrument_id: 标的 ID
        direction: 方向 ("buy" / "sell")
        entry_date: 入场日期
        exit_date: 出场日期 (None = 未平仓)
        holding_days: 持仓天数 (None = 未平仓)
        return_pct: 收益率 (%) (None = 未平仓)
        gross_pnl: 毛利润 (None = 未平仓)
        net_pnl: 净利润 (None = 未平仓)
        fees: 累计费用

    """

    trade_id: str
    instrument_id: InstrumentId
    direction: str
    entry_date: str
    exit_date: str | None
    holding_days: int | None
    return_pct: float | None
    gross_pnl: float | None
    net_pnl: float | None
    fees: float


@dataclass(frozen=True)
class AggregatedTradeStatistics:
    """
    汇总交易统计 — 从已平仓 TradeRecord 序列聚合计算.

    Attributes:
        total_trades: 总交易笔数
        long_trades: 多头交易笔数
        short_trades: 空头交易笔数
        win_trades: 盈利交易笔数
        loss_trades: 亏损交易笔数
        win_rate: 胜率 (%)
        profit_factor: 盈亏比（毛利润之和 / |毛亏损之和|）
        avg_win: 平均盈利交易毛利润
        avg_loss: 平均亏损交易毛利润（正数）
        avg_win_loss_ratio: 平均盈利/平均亏损 比
        max_consecutive_wins: 最大连续盈利次数
        max_consecutive_losses: 最大连续亏损次数
        avg_holding_days: 平均持仓天数
        median_holding_days: 中位持仓天数
        best_trade: 最佳交易毛利润
        worst_trade: 最差交易毛利润（负数）
        avg_trade_return_pct: 平均交易收益率 (%)

    """

    total_trades: int
    long_trades: int
    short_trades: int
    win_trades: int
    loss_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_win_loss_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    avg_holding_days: float
    median_holding_days: float
    best_trade: float
    worst_trade: float
    avg_trade_return_pct: float


@dataclass(frozen=True)
class AlphaStatistics:
    """
    绩效分析统计 — 从 NAV 序列 + 基准 NAV 序列计算.

    Attributes:
        annualized_return: 年化收益率 (%)
        annualized_volatility: 年化波动率 (%)
        sharpe_ratio: 夏普比率
        sortino_ratio: 索提诺比率
        max_drawdown: 最大回撤 (%，负数)
        max_drawdown_duration_days: 最大回撤持续天数
        calmar_ratio: 卡玛比率
        information_ratio: 信息比率 (None = 无基准)
        tracking_error: 跟踪误差 (%，None = 无基准)
        beta: Beta 系数 (None = 无基准)
        alpha_annualized: 年化 Alpha (%，None = 无基准)
        total_turnover: 总换手率
        avg_turnover_per_rebalance: 每次再平衡平均换手率
        total_fees: 总手续费
        net_return_after_cost: 扣费后净收益率 (%)
        cost_drag: 成本拖累 (%)

    """

    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: int
    calmar_ratio: float
    information_ratio: float | None
    tracking_error: float | None
    beta: float | None
    alpha_annualized: float | None
    total_turnover: float
    avg_turnover_per_rebalance: float
    total_fees: float
    net_return_after_cost: float
    cost_drag: float


@dataclass(frozen=True)
class BacktestReport:
    """
    完整回测报告 — 汇聚所有统计维度.

    Attributes:
        run_id: 回测运行 ID
        period: 回测期间 (start_date, end_date)
        initial_cash: 初始资金
        final_nav: 最终净值
        trade_stats: 逐笔交易统计
        portfolio_stats: 每日组合统计
        aggregated_trade_stats: 汇总交易统计
        alpha_stats: 绩效分析统计
        nav_series: 每日 NAV 序列 (trade_date, nav)
        trade_log: 交易记录
        fill_log: 成交记录
        risk_log: PostTrade 风控扫描记录
        pre_trade_log: PreTrade 订单校验决策记录

    """

    run_id: str
    period: tuple[str, str]
    initial_cash: float
    final_nav: float
    trade_stats: tuple[TradeStatistics, ...]
    portfolio_stats: tuple[PortfolioStatistics, ...]
    aggregated_trade_stats: AggregatedTradeStatistics
    alpha_stats: AlphaStatistics
    nav_series: tuple[tuple[str, float], ...]
    trade_log: tuple[TradeRecord, ...]
    fill_log: tuple[FillEvent, ...]
    risk_log: tuple[RiskScanRecord, ...] = ()
    pre_trade_log: tuple[PreTradeDecisionRecord, ...] = ()
