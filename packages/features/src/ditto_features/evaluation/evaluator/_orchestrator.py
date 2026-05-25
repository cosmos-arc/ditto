"""Factor evaluation orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import polars as pl
from ditto_kernel.tracing import traced

from ditto_features.evaluation.contracts import (
    ClosePriceProvider,
    ForwardReturnProvider,
    RiskFactorProvider,
)
from ditto_features.evaluation.evaluator._helpers import (
    compute_ic_decay_safe,
    compute_quantile_annual_returns,
    empty_report,
    estimate_avg_turnover,
    prepare_data,
    resolve_period,
)
from ditto_features.evaluation.metrics import (
    factor_exposure,
    fama_macbeth,
    grinold_kahn_ir,
    ic_autocorrelation,
    ic_summary,
    long_short_returns,
    net_returns,
    orthogonalize,
    pearson_ic,
    performance_attribution,
    quantile_returns,
    rank_ic,
    regime_adjusted_ic,
    sub_period_ic,
    turnover_adjusted_ir,
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
    "FactorEvaluator",
]

DEFAULT_IC_LAGS: list[int] = [1, 2, 3, 5, 10, 20]
DEFAULT_PERIODS_PER_YEAR = 244


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
class _PreparedData:
    """清洗后的输入数据 + 元信息。"""

    factor_df: pl.DataFrame
    return_df: pl.DataFrame
    n_dates: int


@dataclass(frozen=True)
class _ICMetrics:
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
class _QuantileMetrics:
    """分位收益中间结果。"""

    q_ret_df: pl.DataFrame
    long_short: LongShortResult
    quantile_annual_returns: dict[int, float]
    avg_turnover: float
    net_return_after_cost: float


@dataclass(frozen=True)
class _OptionalAnalysis:
    """可选分析中间结果。"""

    fama_macbeth: FamaMacBethResult | None
    factor_exposure: FactorExposureResult | None
    regime_ic: RegimeICResult | None
    performance_attribution: PerformanceAttributionResult | None


class FactorEvaluator:
    """Factor evaluation orchestrator: coordinates forward returns and metrics."""

    def __init__(
        self,
        forward_return_provider: ForwardReturnProvider,
        *,
        close_price_provider: ClosePriceProvider | None = None,
        risk_factor_provider: RiskFactorProvider | None = None,
        risk_factor_ids: list[str] | None = None,
    ) -> None:
        self._fr_provider = forward_return_provider
        self._cp_provider = close_price_provider
        self._rf_provider = risk_factor_provider
        self._rf_ids = risk_factor_ids or []

    @traced("analytics.evaluation.evaluate")
    def evaluate(
        self,
        factor_df: pl.DataFrame,
        config: EvaluationConfig | None = None,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> FactorEvaluationReport:
        """
        End-to-end factor evaluation.

        Steps:
        1. Data preparation (join + null cleanup)
        2. Rank IC + Pearson IC -> ICSummary (IR layer 1)
        3. IC decay + half-life
        4. IC autocorrelation (lag-1 for IR layer 3)
        5. Turnover-adjusted IR (IR layer 3)
        6. Grinold-Kahn IR (IR layer 3)
        7. Quantile returns -> LongShortResult (IR layer 2)
        8. Sub-period IC stability
        9. Assemble report
        """
        effective_config = config or EvaluationConfig()
        return self._evaluate_impl(factor_df, effective_config, start, end)

    def _evaluate_impl(
        self,
        factor_df: pl.DataFrame,
        config: EvaluationConfig,
        start: str | None,
        end: str | None,
    ) -> FactorEvaluationReport:
        """Core evaluation logic."""
        effective_start, effective_end = resolve_period(factor_df, start, end)
        ppw = config.periods_per_year

        # 数据准备
        prepared = self._prepare_factor_data(
            factor_df,
            config,
            start=effective_start,
            end=effective_end,
        )
        if isinstance(prepared, FactorEvaluationReport):
            return prepared

        # 分步计算各项指标
        ic_data = self._compute_ic_metrics(
            prepared,
            config=config,
            effective_start=effective_start,
            effective_end=effective_end,
            ppw=ppw,
        )
        q_data = self._compute_quantile_metrics(
            prepared,
            config=config,
            ppw=ppw,
        )
        opt_data = self._compute_optional_analysis(
            prepared,
            rank_ic_df=ic_data.rank_ic_df,
            q_ret_df=q_data.q_ret_df,
            config=config,
            effective_start=effective_start,
            effective_end=effective_end,
            ppw=ppw,
        )

        return self._assemble_report(
            config=config,
            period=(effective_start, effective_end),
            n_dates=prepared.n_dates,
            n_observations=prepared.factor_df.height,
            ic_data=ic_data,
            q_data=q_data,
            opt_data=opt_data,
        )

    def _prepare_factor_data(
        self,
        factor_df: pl.DataFrame,
        config: EvaluationConfig,
        *,
        start: str,
        end: str,
    ) -> FactorEvaluationReport | _PreparedData:
        """计算远期收益、清洗数据；空数据时返回空报告。"""
        return_df = self._fr_provider.compute(
            asset_class=config.asset_class,
            start=start,
            end=end,
            holding_period=config.holding_period,
            adj=config.adj,
        )
        factor_df_clean, return_df_clean = prepare_data(
            factor_df,
            return_df,
            start=start,
            end=end,
        )
        if factor_df_clean.height == 0:
            return empty_report(
                factor_id="unknown",
                factor_version=1,
                period=(start, end),
                holding_period=config.holding_period,
                n_quantiles=config.n_quantiles,
            )
        n_dates = factor_df_clean.select(
            pl.col("trade_date").n_unique(),
        ).item()
        return _PreparedData(
            factor_df=factor_df_clean,
            return_df=return_df_clean,
            n_dates=n_dates,
        )

    def _compute_ic_metrics(
        self,
        data: _PreparedData,
        *,
        config: EvaluationConfig,
        effective_start: str,
        effective_end: str,
        ppw: int,
    ) -> _ICMetrics:
        """IR Layer 1: IC 分析 + IR Layer 3: Turnover IR / GK IR."""
        effective_lags = config.ic_lags or DEFAULT_IC_LAGS
        rank_ic_df = rank_ic(data.factor_df, data.return_df)
        rank_ic_summary = ic_summary(rank_ic_df)
        pearson_ic_summary = ic_summary(pearson_ic(data.factor_df, data.return_df))

        # IC decay + half-life
        close_df = self._resolve_close_df(config, effective_start, effective_end)
        decay_results, half_life = compute_ic_decay_safe(
            data.factor_df,
            effective_lags,
            close_df=close_df,
        )

        # IC 自相关
        ic_acf = ic_autocorrelation(rank_ic_df, max_lag=config.ic_autocorr_max_lag)
        ic_autocorr_lag1 = ic_acf[0][1] if ic_acf else 0.0

        # IR Layer 3: Turnover-adjusted IR + Grinold-Kahn IR
        t_ir = turnover_adjusted_ir(
            mean_ic=rank_ic_summary.mean,
            ic_autocorr_lag1=ic_autocorr_lag1,
            rebalance_freq=config.rebalance_freq,
        )
        breadth = data.n_dates * (config.n_quantiles - 1) / config.n_quantiles
        gk_ir = grinold_kahn_ir(
            mean_ic=rank_ic_summary.mean,
            ic_std=rank_ic_summary.std,
            ic_autocorr_lag1=ic_autocorr_lag1,
            breadth=breadth,
            rebalance_freq=config.rebalance_freq,
            periods_per_year=ppw,
        )

        return _ICMetrics(
            rank_ic_df=rank_ic_df,
            rank_ic_summary=rank_ic_summary,
            pearson_ic_summary=pearson_ic_summary,
            ic_decay=decay_results,
            ic_half_life=half_life,
            ic_autocorrelation=ic_acf,
            turnover_adjusted_ir=t_ir,
            grinold_kahn_ir=gk_ir,
            sub_period_ic=sub_period_ic(rank_ic_df),
        )

    def _resolve_close_df(
        self,
        config: EvaluationConfig,
        effective_start: str,
        effective_end: str,
    ) -> pl.DataFrame | None:
        """获取收盘价数据（如果 provider 可用）。"""
        if self._cp_provider is None:
            return None
        return self._cp_provider.get_close_prices(
            asset_class=config.asset_class,
            start=effective_start,
            end=effective_end,
            adj=config.adj,
        )

    def _compute_quantile_metrics(
        self,
        data: _PreparedData,
        *,
        config: EvaluationConfig,
        ppw: int,
    ) -> _QuantileMetrics:
        """IR Layer 2: 分位收益 + Long-Short + 换手率 + 净收益."""
        q_ret_df = quantile_returns(
            data.factor_df,
            data.return_df,
            n_quantiles=config.n_quantiles,
        )
        ls_result = long_short_returns(
            q_ret_df,
            risk_free_rate=config.risk_free_rate,
            periods_per_year=ppw,
        )

        quantile_annual = compute_quantile_annual_returns(
            q_ret_df,
            periods_per_year=ppw,
        )
        avg_turnover = estimate_avg_turnover(q_ret_df)
        gross_return = ls_result.annual_return / 100.0
        net_ret = net_returns(gross_return, avg_turnover, config.cost_bps)

        return _QuantileMetrics(
            q_ret_df=q_ret_df,
            long_short=ls_result,
            quantile_annual_returns=quantile_annual,
            avg_turnover=avg_turnover,
            net_return_after_cost=net_ret,
        )

    def _compute_optional_analysis(
        self,
        data: _PreparedData,
        *,
        rank_ic_df: pl.DataFrame,
        q_ret_df: pl.DataFrame,
        config: EvaluationConfig,
        effective_start: str,
        effective_end: str,
        ppw: int,
    ) -> _OptionalAnalysis:
        """可选分析: Fama-MacBeth / 因子暴露 / 情景 IC / 绩效归因."""
        # Fama-MacBeth 回归和因子暴露分析
        fm_result: FamaMacBethResult | None = None
        fe_result: FactorExposureResult | None = None
        risk_dfs = self._resolve_risk_dfs(config, effective_start, effective_end)
        if risk_dfs:
            if config.run_fama_macbeth:
                fm_result = fama_macbeth(
                    data.factor_df,
                    data.return_df,
                    risk_factors=risk_dfs,
                )
            if config.run_exposure_analysis:
                fe_result = factor_exposure(
                    data.factor_df,
                    risk_dfs,
                    return_df=data.return_df,
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

        return _OptionalAnalysis(
            fama_macbeth=fm_result,
            factor_exposure=fe_result,
            regime_ic=regime_ic_result,
            performance_attribution=pa_result,
        )

    def _assemble_report(
        self,
        *,
        config: EvaluationConfig,
        period: tuple[str, str],
        n_dates: int,
        n_observations: int,
        ic_data: _ICMetrics,
        q_data: _QuantileMetrics,
        opt_data: _OptionalAnalysis,
    ) -> FactorEvaluationReport:
        """组装 FactorEvaluationReport."""
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

    def _resolve_risk_dfs(
        self,
        config: EvaluationConfig,
        effective_start: str,
        effective_end: str,
    ) -> dict[str, pl.DataFrame]:
        """获取风险因子数据（条件满足时）。"""
        if (
            not (config.run_fama_macbeth or config.run_exposure_analysis)
            or self._rf_provider is None
            or not self._rf_ids
        ):
            return {}
        return self._rf_provider.get_risk_factors(
            self._rf_ids,
            effective_start,
            effective_end,
        )

    def evaluate_orthogonal(
        self,
        target_df: pl.DataFrame,
        other_factor_dfs: list[pl.DataFrame],
        *,
        method: str = "sequential",
        min_cross_section: int = 30,
    ) -> pl.DataFrame:
        """Factor orthogonalization evaluation."""
        if not other_factor_dfs:
            return target_df.select(
                pl.col("trade_date"),
                pl.col("instrument_id"),
                pl.col("value").alias("orthogonalized_value"),
            )

        # Build long-format factors DataFrame with factor_name column,
        # as required by the orthogonalize function.
        long_frames: list[pl.DataFrame] = []
        for idx, other in enumerate(other_factor_dfs):
            long_frames.append(
                other.select(
                    pl.col("trade_date"),
                    pl.col("instrument_id"),
                    pl.col("value"),
                    pl.lit(f"factor_{idx}").alias("factor_name"),
                ),
            )
        factors_df = pl.concat(long_frames)

        return orthogonalize(
            target_df,
            factors_df,
            method=method,
            min_cross_section=min_cross_section,
        )
