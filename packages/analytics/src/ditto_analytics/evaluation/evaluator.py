"""Factor evaluation orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import polars as pl
import polars.exceptions as pl_exc

from ditto_analytics.evaluation.metrics import (
    factor_exposure,
    fama_macbeth,
    grinold_kahn_ir,
    ic_autocorrelation,
    ic_decay,
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
from ditto_analytics.evaluation.report import (
    FactorEvaluationReport,
    FactorExposureResult,
    FamaMacBethResult,
    ICSummary,
    LongShortResult,
    PerformanceAttributionResult,
    RegimeICResult,
    TailRiskMetrics,
)

__all__ = [
    "ClosePriceProvider",
    "EvaluationConfig",
    "FactorEvaluator",
    "ForwardReturnProvider",
    "RiskFactorProvider",
]

DEFAULT_IC_LAGS: list[int] = [1, 2, 3, 5, 10, 20]
DEFAULT_PERIODS_PER_YEAR = 244
_MIN_DATES_FOR_TURNOVER = 2


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


class ForwardReturnProvider(Protocol):
    """Protocol for providing forward return data."""

    def compute(
        self,
        asset_class: str,
        start: str,
        end: str,
        holding_period: int = 5,
        adj: str = "none",
    ) -> pl.DataFrame:
        """Compute forward returns for the given parameters."""
        ...


class ClosePriceProvider(Protocol):
    """Protocol for providing close price data for IC decay computation."""

    def get_close_prices(
        self,
        asset_class: str,
        start: str,
        end: str,
        adj: str = "none",
    ) -> pl.DataFrame:
        """Return close prices as ``[date, entity, close]``."""
        ...


class RiskFactorProvider(Protocol):
    """Provide risk factor data for Fama-MacBeth and factor exposure."""

    def get_risk_factors(
        self,
        factor_ids: list[str],
        start: str,
        end: str,
    ) -> dict[str, pl.DataFrame]:
        """
        Retrieve risk factor DataFrames for the given IDs and date range.

        Args:
            factor_ids: List of risk factor identifiers to retrieve.
            start: Start date string (inclusive).
            end: End date string (inclusive).

        Returns:
            ``{factor_id: DataFrame[date, entity, value]}`` mapping.

        """
        ...


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
        effective_start, effective_end = _resolve_period(factor_df, start, end)
        effective_lags = config.ic_lags or DEFAULT_IC_LAGS
        ppw = config.periods_per_year

        # Compute forward returns
        return_df = self._fr_provider.compute(
            asset_class=config.asset_class,
            start=effective_start,
            end=effective_end,
            holding_period=config.holding_period,
            adj=config.adj,
        )

        # Data preparation
        factor_df_clean, return_df_clean = _prepare_data(
            factor_df,
            return_df,
            start=effective_start,
            end=effective_end,
        )

        if factor_df_clean.height == 0:
            return _empty_report(
                factor_id="unknown",
                factor_version=1,
                period=(effective_start, effective_end),
                holding_period=config.holding_period,
                n_quantiles=config.n_quantiles,
            )

        n_dates = factor_df_clean.select(
            pl.col("trade_date").n_unique(),
        ).item()

        # IR Layer 1: IC analysis
        rank_ic_df = rank_ic(factor_df_clean, return_df_clean)
        pearson_ic_df = pearson_ic(factor_df_clean, return_df_clean)
        rank_ic_summary = ic_summary(rank_ic_df)
        pearson_ic_summary = ic_summary(pearson_ic_df)

        # IC decay + half-life
        close_df = None
        if self._cp_provider is not None:
            close_df = self._cp_provider.get_close_prices(
                asset_class=config.asset_class,
                start=effective_start,
                end=effective_end,
                adj=config.adj,
            )
        decay_results, half_life = _compute_ic_decay_safe(
            factor_df_clean,
            effective_lags,
            close_df=close_df,
        )

        # IC autocorrelation
        ic_acf = ic_autocorrelation(
            rank_ic_df,
            max_lag=config.ic_autocorr_max_lag,
        )
        ic_autocorr_lag1 = ic_acf[0][1] if ic_acf else 0.0

        # IR Layer 3: Turnover-adjusted IR
        t_ir = turnover_adjusted_ir(
            mean_ic=rank_ic_summary.mean,
            ic_autocorr_lag1=ic_autocorr_lag1,
            rebalance_freq=config.rebalance_freq,
        )

        # IR Layer 3: Grinold-Kahn IR
        breadth = n_dates * (config.n_quantiles - 1) / config.n_quantiles
        gk_ir = grinold_kahn_ir(
            mean_ic=rank_ic_summary.mean,
            ic_std=rank_ic_summary.std,
            ic_autocorr_lag1=ic_autocorr_lag1,
            breadth=breadth,
            rebalance_freq=config.rebalance_freq,
            periods_per_year=ppw,
        )

        # IR Layer 2: Quantile returns + Long-Short
        q_ret_df = quantile_returns(
            factor_df_clean,
            return_df_clean,
            n_quantiles=config.n_quantiles,
        )
        ls_result = long_short_returns(
            q_ret_df,
            risk_free_rate=config.risk_free_rate,
            periods_per_year=ppw,
        )

        # Quantile annual returns
        quantile_annual = _compute_quantile_annual_returns(
            q_ret_df,
            periods_per_year=ppw,
        )

        # Turnover and net returns
        avg_turnover = _estimate_avg_turnover(q_ret_df)
        gross_return = ls_result.annual_return / 100.0
        net_ret = net_returns(gross_return, avg_turnover, config.cost_bps)

        # Sub-period IC
        sub_ic = sub_period_ic(rank_ic_df)

        # Fama-MacBeth regression and factor exposure analysis (optional)
        fm_result: FamaMacBethResult | None = None
        fe_result: FactorExposureResult | None = None
        risk_dfs: dict[str, pl.DataFrame] = {}
        if (
            (config.run_fama_macbeth or config.run_exposure_analysis)
            and self._rf_provider is not None
            and self._rf_ids
        ):
            risk_dfs = self._rf_provider.get_risk_factors(
                self._rf_ids,
                effective_start,
                effective_end,
            )
        if risk_dfs:
            if config.run_fama_macbeth:
                fm_result = fama_macbeth(
                    factor_df_clean,
                    return_df_clean,
                    risk_factors=risk_dfs,
                )
            if config.run_exposure_analysis:
                fe_result = factor_exposure(
                    factor_df_clean,
                    risk_dfs,
                    return_df=return_df_clean,
                )

        # Regime-adjusted IC (optional)
        regime_ic_result: RegimeICResult | None = None
        if config.run_regime_ic:
            regime_ic_result = regime_adjusted_ic(rank_ic_df)

        # Performance attribution (optional)
        pa_result: PerformanceAttributionResult | None = None
        if config.run_performance_attribution:
            pa_result = performance_attribution(
                q_ret_df,
                periods_per_year=ppw,
            )

        return FactorEvaluationReport(
            factor_id="unknown",
            factor_version=1,
            evaluation_period=(effective_start, effective_end),
            holding_period=config.holding_period,
            n_quantiles=config.n_quantiles,
            rank_ic_summary=rank_ic_summary,
            pearson_ic_summary=pearson_ic_summary,
            ic_decay=decay_results,
            ic_half_life=half_life,
            ic_autocorrelation=ic_acf,
            quantile_annual_returns=quantile_annual,
            long_short=ls_result,
            avg_turnover=avg_turnover,
            net_return_after_cost=net_ret,
            turnover_adjusted_ir=t_ir,
            grinold_kahn_ir=gk_ir,
            sub_period_ic=sub_ic,
            fama_macbeth=fm_result,
            factor_exposure=fe_result,
            regime_ic=regime_ic_result,
            performance_attribution=pa_result,
            n_observations=factor_df_clean.height,
            n_dates=n_dates,
            computed_at=datetime.now(UTC).isoformat(),
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


def _resolve_period(
    factor_df: pl.DataFrame,
    start: str | None,
    end: str | None,
) -> tuple[str, str]:
    """Resolve evaluation period from explicit bounds or data range."""
    if "trade_date" in factor_df.columns:
        dates = factor_df.select(
            pl.col("trade_date").min().alias("min"),
            pl.col("trade_date").max().alias("max"),
        )
        effective_start = start or str(dates["min"][0])
        effective_end = end or str(dates["max"][0])
    else:
        effective_start = start or "1970-01-01"
        effective_end = end or "2099-12-31"
    return effective_start, effective_end


def _prepare_data(
    factor_df: pl.DataFrame,
    return_df: pl.DataFrame,
    *,
    start: str | None = None,
    end: str | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Filter date range and drop null values."""
    date_col = "trade_date"

    # Build temporal bounds that are compatible with both Date and Utf8 columns.
    start_lit = pl.lit(start).cast(pl.Date) if start is not None else None
    end_lit = pl.lit(end).cast(pl.Date) if end is not None else None

    if start_lit is not None and date_col in factor_df.columns:
        factor_df = factor_df.filter(pl.col(date_col) >= start_lit)
    if end_lit is not None and date_col in factor_df.columns:
        factor_df = factor_df.filter(pl.col(date_col) <= end_lit)
    if start_lit is not None and date_col in return_df.columns:
        return_df = return_df.filter(pl.col(date_col) >= start_lit)
    if end_lit is not None and date_col in return_df.columns:
        return_df = return_df.filter(pl.col(date_col) <= end_lit)

    factor_df = factor_df.drop_nulls(subset=["value", date_col])
    return_df = return_df.drop_nulls(subset=["forward_return", date_col])

    return factor_df, return_df


def _compute_ic_decay_safe(
    factor_df: pl.DataFrame,
    lags: list[int],
    *,
    close_df: pl.DataFrame | None = None,
) -> tuple[list[tuple[int, float]], float | None]:
    """
    Safely compute IC decay, returning empty list on failure.

    When *close_df* is provided, forward returns are derived from actual
    close prices (correct IC decay).  When omitted, factor values are
    used as pseudo-close (computes factor autocorrelation, not true IC
    decay) — kept for backward compatibility but semantically wrong.
    """
    try:
        if close_df is not None:
            return ic_decay(
                factor_df,
                close_df,
                lags=lags,
                factor_col="value",
            )
        # Fallback: use factor values as pseudo-close (legacy behavior)
        pseudo_close = factor_df.select(
            pl.col("trade_date"),
            pl.col("instrument_id"),
            pl.col("value").alias("close"),
        )
        return ic_decay(
            pseudo_close,
            pseudo_close,
            lags=lags,
            factor_col="close",
        )
    except (pl_exc.ColumnNotFoundError, pl_exc.ComputeError, ValueError):
        return [], None


def _compute_quantile_annual_returns(
    q_ret_df: pl.DataFrame,
    *,
    periods_per_year: int = 244,
) -> dict[int, float]:
    """Compute annualized return per quantile group."""
    if q_ret_df.height == 0:
        return {}
    result: dict[int, float] = {}
    for q in q_ret_df.select(pl.col("quantile").unique()).to_series().sort():
        group = q_ret_df.filter(pl.col("quantile") == q)
        mean_ret = group.select(pl.col("mean_return").mean()).item()
        if mean_ret is None:
            continue
        annual = float(mean_ret) * periods_per_year
        result[int(q)] = round(annual, 6)
    return result


def _estimate_avg_turnover(
    q_ret_df: pl.DataFrame,
) -> float:
    """Estimate average turnover from quantile migration."""
    if q_ret_df.height < _MIN_DATES_FOR_TURNOVER:
        return 0.0

    try:
        dates = sorted(
            q_ret_df.select(pl.col("trade_date").unique()).to_series().to_list(),
        )
        if len(dates) < _MIN_DATES_FOR_TURNOVER:
            return 0.0

        migrations: list[float] = []
        for i in range(1, len(dates)):
            prev = q_ret_df.filter(pl.col("trade_date") == dates[i - 1])
            curr = q_ret_df.filter(pl.col("trade_date") == dates[i])
            # If we had weight data we'd compute actual turnover;
            # here we estimate from quantile return stability
            curr_mean = curr.select(pl.col("mean_return").mean()).item() or 0
            prev_mean = prev.select(pl.col("mean_return").mean()).item() or 0
            avg_change = abs(curr_mean - prev_mean)
            migrations.append(avg_change)

        return float(sum(migrations) / len(migrations)) if migrations else 0.0
    except (pl_exc.ComputeError, TypeError, IndexError):
        return 0.0


def _empty_report(
    *,
    factor_id: str,
    factor_version: int,
    period: tuple[str, str],
    holding_period: int,
    n_quantiles: int,
) -> FactorEvaluationReport:
    """Create an empty report for degenerate cases."""
    empty_ic = ICSummary(
        mean=0.0,
        std=0.0,
        icir=0.0,
        t_stat=0.0,
        p_value=1.0,
        win_rate=0.0,
    )
    empty_tail = TailRiskMetrics(
        cvar_95=0.0,
        cvar_99=0.0,
        skewness=0.0,
        kurtosis=0.0,
        max_single_day_loss=0.0,
    )
    empty_ls = LongShortResult(
        annual_return=0.0,
        annual_volatility=0.0,
        sharpe=0.0,
        portfolio_ir=0.0,
        sortino=0.0,
        max_drawdown=0.0,
        calmar=0.0,
        tail_risk=empty_tail,
    )
    return FactorEvaluationReport(
        factor_id=factor_id,
        factor_version=factor_version,
        evaluation_period=period,
        holding_period=holding_period,
        n_quantiles=n_quantiles,
        rank_ic_summary=empty_ic,
        pearson_ic_summary=empty_ic,
        ic_decay=[],
        ic_half_life=None,
        ic_autocorrelation=[],
        quantile_annual_returns={},
        long_short=empty_ls,
        avg_turnover=0.0,
        net_return_after_cost=0.0,
        turnover_adjusted_ir=0.0,
        grinold_kahn_ir=0.0,
        sub_period_ic={},
        n_observations=0,
        n_dates=0,
        computed_at=datetime.now(UTC).isoformat(),
        regime_ic=None,
        performance_attribution=None,
    )
