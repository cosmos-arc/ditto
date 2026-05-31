"""Report assembly for factor evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import polars as pl

from ditto_features.evaluation.metrics import (
    factor_exposure,
    fama_macbeth,
    performance_attribution,
    regime_adjusted_ic,
)
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    FactorExposureResult,
    FamaMacBethResult,
    ICSummary,
    LongShortResult,
    PerformanceAttributionResult,
    RegimeICResult,
)

__all__ = [
    "EvaluationConfig",
    "ICMetricsData",
    "OptionalAnalysisData",
    "QuantileMetricsData",
    "assemble_report",
    "compute_optional_analysis",
]


@dataclass(frozen=True)
class EvaluationConfig:
    """Configuration parameters for factor evaluation."""

    asset_class: str = "stock"
    adj: str = "none"
    holding_period: int = 5
    n_quantiles: int = 5
    ic_lags: list[int] | None = field(default=None)
    ic_autocorr_max_lag: int = 10
    risk_free_rate: float = 0.0
    cost_bps: float = 20.0
    rebalance_freq: int = 5
    periods_per_year: int = 244
    run_fama_macbeth: bool = False
    run_exposure_analysis: bool = False
    run_regime_ic: bool = False
    run_performance_attribution: bool = False


@dataclass(frozen=True)
class ICMetricsData:
    """IC 分析中间结果。"""

    rank_ic_df: pl.DataFrame
    rank_ic_summary: ICSummary
    pearson_ic_summary: ICSummary
    ic_decay: list[tuple[int, float]]
    ic_half_life: float | None
    ic_autocorrelation: list[tuple[int, float]]
    turnover_adjusted_ir: float
    grinold_kahn_ir: float
    sub_period_ic: dict[str, ICSummary]


@dataclass(frozen=True)
class QuantileMetricsData:
    """分位收益中间结果。"""

    q_ret_df: pl.DataFrame
    long_short: LongShortResult
    quantile_annual_returns: dict[int, float]
    avg_turnover: float
    net_return_after_cost: float


@dataclass(frozen=True)
class OptionalAnalysisData:
    """可选分析中间结果。"""

    fama_macbeth: FamaMacBethResult | None
    factor_exposure: FactorExposureResult | None
    regime_ic: RegimeICResult | None
    performance_attribution: PerformanceAttributionResult | None


def compute_optional_analysis(
    *,
    factor_df: pl.DataFrame,
    return_df: pl.DataFrame,
    rank_ic_df: pl.DataFrame,
    q_ret_df: pl.DataFrame,
    config: EvaluationConfig,
    risk_dfs: dict[str, pl.DataFrame],
    ppw: int,
) -> OptionalAnalysisData:
    """计算可选分析: Fama-MacBeth / 因子暴露 / 情景 IC / 绩效归因."""
    # Fama-MacBeth 回归和因子暴露分析
    fm_result: FamaMacBethResult | None = None
    fe_result: FactorExposureResult | None = None
    if risk_dfs:
        if config.run_fama_macbeth:
            fm_result = fama_macbeth(
                factor_df,
                return_df,
                risk_factors=risk_dfs,
            )
        if config.run_exposure_analysis:
            fe_result = factor_exposure(
                factor_df,
                risk_dfs,
                return_df=return_df,
            )

    # 情景调整 IC
    regime_ic_result: RegimeICResult | None = None
    if config.run_regime_ic:
        regime_ic_result = regime_adjusted_ic(rank_ic_df)

    # 绩效归因
    pa_result: PerformanceAttributionResult | None = None
    if config.run_performance_attribution:
        pa_result = performance_attribution(
            q_ret_df,
            periods_per_year=ppw,
        )

    return OptionalAnalysisData(
        fama_macbeth=fm_result,
        factor_exposure=fe_result,
        regime_ic=regime_ic_result,
        performance_attribution=pa_result,
    )


def assemble_report(
    *,
    config: EvaluationConfig,
    period: tuple[str, str],
    n_dates: int,
    n_observations: int,
    ic_data: ICMetricsData,
    q_data: QuantileMetricsData,
    opt_data: OptionalAnalysisData,
) -> FactorEvaluationReport:
    """组装 FactorEvaluationReport。"""
    return FactorEvaluationReport(
        factor_id="unknown",
        factor_version=1,
        evaluation_period=period,
        holding_period=config.holding_period,
        n_quantiles=config.n_quantiles,
        rank_ic_summary=ic_data.rank_ic_summary,
        pearson_ic_summary=ic_data.pearson_ic_summary,
        ic_decay=ic_data.ic_decay,
        ic_half_life=ic_data.ic_half_life,
        ic_autocorrelation=ic_data.ic_autocorrelation,
        quantile_annual_returns=q_data.quantile_annual_returns,
        long_short=q_data.long_short,
        avg_turnover=q_data.avg_turnover,
        net_return_after_cost=q_data.net_return_after_cost,
        turnover_adjusted_ir=ic_data.turnover_adjusted_ir,
        grinold_kahn_ir=ic_data.grinold_kahn_ir,
        sub_period_ic=ic_data.sub_period_ic,
        fama_macbeth=opt_data.fama_macbeth,
        factor_exposure=opt_data.factor_exposure,
        regime_ic=opt_data.regime_ic,
        performance_attribution=opt_data.performance_attribution,
        n_observations=n_observations,
        n_dates=n_dates,
        computed_at=datetime.now(UTC).isoformat(),
    )
