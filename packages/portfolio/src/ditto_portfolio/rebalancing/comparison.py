"""
StrategyComparisonReport — 策略对比报告.

比较两次回测运行的绩效指标，计算差异并判定改进/退化方向。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_portfolio.rebalancing.report_views import BacktestReportView

__all__ = [
    "MetricsDelta",
    "StrategyComparisonReport",
    "compare_reports",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricsDelta:
    """
    两个回测运行之间的绩效指标差异.

    Attributes:
        annualized_return: 年化收益率差异 (compare - baseline, 百分点)
        sharpe_ratio: 夏普比率差异
        sortino_ratio: 索提诺比率差异
        max_drawdown: 最大回撤差异 (正值 = 更好，即 less negative)
        total_turnover: 总换手率差异
        total_fees: 总费用差异
        cost_drag: 成本拖累差异
        final_nav: 最终净值差异 (绝对值，非百分比)
        total_trades: 总交易笔数差异

    """

    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    total_turnover: float
    total_fees: float
    cost_drag: float
    final_nav: float
    total_trades: int


@dataclass(frozen=True)
class StrategyComparisonReport:
    """
    策略对比报告 — 汇聚差异与改进/退化判定.

    Attributes:
        baseline_run_id: 基准回测运行 ID
        compare_run_id: 对比回测运行 ID
        metrics_delta: 绩效指标差异
        improved: 改进的指标名称列表
        degraded: 退化的指标名称列表

    """

    baseline_run_id: str
    compare_run_id: str
    metrics_delta: MetricsDelta
    improved: tuple[str, ...]
    degraded: tuple[str, ...]


# ---------------------------------------------------------------------------
# "Higher is better" set — metrics where a positive delta means improvement
# ---------------------------------------------------------------------------

_HIGHER_IS_BETTER: frozenset[str] = frozenset(
    {
        "annualized_return",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "final_nav",
    }
)

# "Lower is better" set — metrics where a negative delta means improvement
_LOWER_IS_BETTER: frozenset[str] = frozenset(
    {
        "total_turnover",
        "total_fees",
        "cost_drag",
    }
)


def _classify_delta(name: str, value: float) -> int:
    """返回 1 (改进), -1 (退化), 0 (无变化)。"""
    if name in _HIGHER_IS_BETTER:
        if value > 0:
            return 1
        if value < 0:
            return -1
    elif name in _LOWER_IS_BETTER:
        if value < 0:
            return 1
        if value > 0:
            return -1
    return 0


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def compare_reports(
    baseline: BacktestReportView,
    compare: BacktestReportView,
) -> StrategyComparisonReport:
    """
    比较两个回测报告，生成差异报告.

    Args:
        baseline: 基准回测报告.
        compare: 对比回测报告.

    Returns:
        StrategyComparisonReport 实例.

    """
    b_alpha = baseline.alpha_stats
    c_alpha = compare.alpha_stats

    delta = MetricsDelta(
        annualized_return=c_alpha.annualized_return - b_alpha.annualized_return,
        sharpe_ratio=c_alpha.sharpe_ratio - b_alpha.sharpe_ratio,
        sortino_ratio=c_alpha.sortino_ratio - b_alpha.sortino_ratio,
        max_drawdown=c_alpha.max_drawdown - b_alpha.max_drawdown,
        total_turnover=c_alpha.total_turnover - b_alpha.total_turnover,
        total_fees=c_alpha.total_fees - b_alpha.total_fees,
        cost_drag=c_alpha.cost_drag - b_alpha.cost_drag,
        final_nav=compare.final_nav - baseline.final_nav,
        total_trades=(
            compare.aggregated_trade_stats.total_trades
            - baseline.aggregated_trade_stats.total_trades
        ),
    )

    improved: list[str] = []
    degraded: list[str] = []

    delta_map: dict[str, float] = {
        "annualized_return": delta.annualized_return,
        "sharpe_ratio": delta.sharpe_ratio,
        "sortino_ratio": delta.sortino_ratio,
        "max_drawdown": delta.max_drawdown,
        "total_turnover": delta.total_turnover,
        "total_fees": delta.total_fees,
        "cost_drag": delta.cost_drag,
        "final_nav": delta.final_nav,
    }

    for name, value in delta_map.items():
        direction = _classify_delta(name, value)
        if direction > 0:
            improved.append(name)
        elif direction < 0:
            degraded.append(name)

    return StrategyComparisonReport(
        baseline_run_id=baseline.run_id,
        compare_run_id=compare.run_id,
        metrics_delta=delta,
        improved=tuple(improved),
        degraded=tuple(degraded),
    )
