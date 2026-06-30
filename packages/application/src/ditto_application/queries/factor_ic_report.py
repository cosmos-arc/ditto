"""
因子 IC 诊断报告 Markdown 渲染（纯函数）.

将 :class:`FactorEvaluationReport` 渲染为人类可读的 Markdown 报告.
本模块位于 application query 层, 可合法依赖 ditto_features 的报告类型;
apps 层通过 :func:`render_factor_ic_markdown` 消费, 不直接导入 capability package.
"""

from __future__ import annotations

from ditto_features.evaluation.report import FactorEvaluationReport

__all__ = ["render_factor_ic_markdown"]


def _fmt_ic(value: float) -> str:
    """格式化 IC/ICIR 数值, 保留 4 位小数."""
    return f"{value:.4f}"


def _fmt_pct(value: float) -> str:
    """格式化百分比数值, 比率转百分比保留 2 位小数."""
    return f"{value * 100:.2f}%"


def _fmt_contract_value(value: str) -> str:
    """格式化报告契约字段, 空值显式标记为 unknown."""
    return value if value else "unknown"


_FOOTER = "> 离线因子评估报告. 结合 IC/分层/换手综合判断, 权重调整由人工决策."


def _contract_section(report: FactorEvaluationReport) -> list[str]:
    """渲染报告契约字段, 便于人工复核数据与样本上下文."""
    start, end = report.evaluation_period
    return [
        "## Contract",
        "",
        "| 字段 | 值 |",
        "|------|----|",
        f"| Factor | `{report.factor_id}` |",
        f"| Version | `{report.factor_version}` |",
        f"| Dataset | `{_fmt_contract_value(report.dataset_id)}` |",
        f"| Catalog Snapshot | `{_fmt_contract_value(report.catalog_snapshot_id)}` |",
        f"| Sample Period | `{start}` ~ `{end}` |",
        f"| Universe | `{_fmt_contract_value(report.universe)}` |",
        f"| Cost Bps | `{report.cost_bps:.2f}` |",
        "",
    ]


def _ic_summary_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 IC Summary 章节 (Rank IC vs Pearson IC 双列表格)."""
    lines = [
        "## IC Summary",
        "",
        "| 指标 | Rank IC | Pearson IC |",
        "|------|---------|------------|",
    ]
    for label, key in (
        ("Mean", "mean"),
        ("Std", "std"),
        ("ICIR", "icir"),
        ("t-stat", "t_stat"),
        ("p-value", "p_value"),
        ("Win Rate", "win_rate"),
    ):
        rank_val = getattr(report.rank_ic_summary, key)
        pear_val = getattr(report.pearson_ic_summary, key)
        if label == "Win Rate":
            lines.append(f"| {label} | {_fmt_pct(rank_val)} | {_fmt_pct(pear_val)} |")
        else:
            lines.append(f"| {label} | {_fmt_ic(rank_val)} | {_fmt_ic(pear_val)} |")
    lines.append("")
    return lines


def _ic_decay_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 IC Decay & Stability 章节."""
    lines = ["## IC Decay", ""]
    if report.ic_half_life is not None:
        lines.append(f"- IC 半衰期: {_fmt_ic(report.ic_half_life)} 天")
    else:
        lines.append("- IC 半衰期: 无法计算")
    if report.ic_decay:
        lines += ["", "| Lag | IC |", "|-----|----|"]
        lines += [f"| {lag} | {_fmt_ic(ic)} |" for lag, ic in report.ic_decay]
        lines.append("")
    if report.ic_autocorrelation:
        lines.append(f"- IC 一阶自相关: {_fmt_ic(report.ic_autocorrelation[0][1])}")
        lines.append("")
    return lines


def _sub_period_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 Sub-period IC 章节 (空 dict 时返回空列表, 由调用方省略)."""
    if not report.sub_period_ic:
        return []
    lines = [
        "## Sub-period IC",
        "",
        "| 区间 | ICIR | Win Rate |",
        "|------|------|----------|",
    ]
    for period, summary in report.sub_period_ic.items():
        lines.append(
            f"| {period} | {_fmt_ic(summary.icir)} | {_fmt_pct(summary.win_rate)} |"
        )
    lines.append("")
    return lines


def _quantile_returns_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 Quantile Returns 章节 (含单调性判断)."""
    sorted_q = sorted(report.quantile_annual_returns)
    lines = ["## Quantile Returns", "", "| 分位 | 年化收益 |", "|------|----------|"]
    for quantile in sorted_q:
        ret = report.quantile_annual_returns[quantile]
        lines.append(f"| Q{quantile} | {_fmt_pct(ret)} |")
    if sorted_q:
        top_q, bottom_q = sorted_q[-1], sorted_q[0]
        top_ret = report.quantile_annual_returns[top_q]
        bottom_ret = report.quantile_annual_returns[bottom_q]
        monotonic = "单调" if top_ret > bottom_ret else "非单调"
        lines += [
            "",
            (
                f"- 最高分位 Q{top_q} ({_fmt_pct(top_ret)}) vs "
                f"最低分位 Q{bottom_q} ({_fmt_pct(bottom_ret)}): {monotonic}"
            ),
        ]
    lines.append("")
    return lines


def _long_short_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 Long-Short Portfolio 章节 (含尾部风险子表)."""
    ls = report.long_short
    lines = [
        "## Long-Short",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| 年化收益 | {_fmt_pct(ls.annual_return)} |",
        f"| 年化波动 | {_fmt_pct(ls.annual_volatility)} |",
        f"| Sharpe | {_fmt_ic(ls.sharpe)} |",
        f"| Portfolio IR | {_fmt_ic(ls.portfolio_ir)} |",
        f"| Sortino | {_fmt_ic(ls.sortino)} |",
        f"| 最大回撤 | {_fmt_pct(ls.max_drawdown)} |",
        f"| Calmar | {_fmt_ic(ls.calmar)} |",
        "",
        "### 尾部风险",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| CVaR 95% | {_fmt_pct(ls.tail_risk.cvar_95)} |",
        f"| CVaR 99% | {_fmt_pct(ls.tail_risk.cvar_99)} |",
        f"| 偏度 | {_fmt_ic(ls.tail_risk.skewness)} |",
        f"| 峰度 | {_fmt_ic(ls.tail_risk.kurtosis)} |",
        f"| 最大单日亏损 | {_fmt_pct(ls.tail_risk.max_single_day_loss)} |",
        "",
    ]
    return lines


def _turnover_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 Turnover & Cost 章节."""
    return [
        "## Turnover",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| 平均换手 | {_fmt_pct(report.avg_turnover)} |",
        f"| 成本后净收益 | {_fmt_pct(report.net_return_after_cost)} |",
        f"| 换手调整 IR | {_fmt_ic(report.turnover_adjusted_ir)} |",
        f"| Grinold-Kahn IR | {_fmt_ic(report.grinold_kahn_ir)} |",
        "",
    ]


def _regime_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 Regime IC 章节 (report.regime_ic 为 None 时返回空列表)."""
    if report.regime_ic is None:
        return []
    lines = [
        "## Regime IC",
        "",
        "| 情景 | ICIR | Win Rate |",
        "|------|------|----------|",
    ]
    for regime, summary in report.regime_ic.regimes.items():
        lines.append(
            f"| {regime} | {_fmt_ic(summary.icir)} | {_fmt_pct(summary.win_rate)} |"
        )
    lines += [
        "",
        f"- IC 趋势: {_fmt_ic(report.regime_ic.ic_trend)}",
        f"- 趋势 p-value: {_fmt_ic(report.regime_ic.ic_trend_p_value)}",
        "",
    ]
    return lines


def _attribution_section(report: FactorEvaluationReport) -> list[str]:
    """渲染 Performance Attribution 章节 (None 时返回空列表)."""
    if report.performance_attribution is None:
        return []
    pa = report.performance_attribution
    return [
        "## Performance Attribution",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| 总收益 | {_fmt_pct(pa.total_return)} |",
        f"| 选股收益 | {_fmt_pct(pa.selection_return)} |",
        f"| 择时收益 | {_fmt_pct(pa.timing_return)} |",
        f"| 年化 Alpha | {_fmt_pct(pa.annual_alpha)} |",
        f"| 跟踪误差 | {_fmt_pct(pa.tracking_error)} |",
        f"| 信息比率 | {_fmt_ic(pa.information_ratio)} |",
        "",
    ]


def render_factor_ic_markdown(report: FactorEvaluationReport) -> str:
    """
    渲染因子 IC 诊断报告为 Markdown.

    纯函数: 无 IO、无副作用, 仅根据 report 字段拼接 Markdown 字符串.
    可选章节 (regime_ic / performance_attribution) 通过 None 守卫按需输出.
    无观测数据时输出简短提示报告.
    """
    if report.n_observations == 0:
        return "\n".join(
            [
                f"# Factor IC Report: {report.factor_id} v{report.factor_version}",
                "",
                "> 无可用观测数据, 无法生成 IC 诊断报告.",
                "",
                _FOOTER,
            ]
        )

    start, end = report.evaluation_period
    lines: list[str] = [
        f"# Factor IC Report: {report.factor_id} v{report.factor_version}",
        "",
        f"- 生成时间: `{report.computed_at}`",
        f"- 评估区间: `{start}` ~ `{end}`",
        "",
        "## Overview",
        "",
        f"- 交易日数: {report.n_dates}",
        f"- 观测数: {report.n_observations}",
        f"- 持有期: {report.holding_period} 天",
        f"- 分层数: {report.n_quantiles}",
        "",
    ]
    lines += _contract_section(report)
    lines += _ic_summary_section(report)
    lines += _ic_decay_section(report)
    lines += _sub_period_section(report)
    lines += _quantile_returns_section(report)
    lines += _long_short_section(report)
    lines += _turnover_section(report)
    lines += _regime_section(report)
    lines += _attribution_section(report)
    lines += ["---", "", _FOOTER]
    return "\n".join(lines)
