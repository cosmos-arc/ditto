"""Helper functions for factor evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import polars.exceptions as pl_exc
from ditto_platform.foundation import logger

from ditto_features.evaluation.metrics import ic_decay
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    ICSummary,
    LongShortResult,
    TailRiskMetrics,
)

_MIN_DATES_FOR_TURNOVER = 2


def resolve_period(
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


def prepare_data(
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


def compute_ic_decay_safe(
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
    decay) to preserve the legacy no-close-data behavior.
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
        logger.debug("IC decay 计算失败, 返回空结果", exc_info=True)
        return [], None


def compute_quantile_annual_returns(
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


def estimate_avg_turnover(
    q_ret_df: pl.DataFrame,
) -> float:
    """Estimate average turnover from quantile migration."""
    if q_ret_df.height < _MIN_DATES_FOR_TURNOVER:
        return 0.0

    try:
        daily = (
            q_ret_df.group_by("trade_date")
            .agg(pl.col("mean_return").mean())
            .sort("trade_date")
        )

        if daily.height < _MIN_DATES_FOR_TURNOVER:
            return 0.0

        migrations = daily.select(pl.col("mean_return").diff().abs().drop_nans())

        return float(migrations.select(pl.col("mean_return").mean()).item()) or 0.0
    except (pl_exc.ComputeError, TypeError, IndexError):
        logger.debug("换手率估算失败, 返回默认值", exc_info=True)
        return 0.0


def empty_report(
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
