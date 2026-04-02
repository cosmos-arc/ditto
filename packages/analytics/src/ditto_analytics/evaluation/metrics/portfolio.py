"""Portfolio analysis functions: quantile returns, long-short, turnover, net returns."""

from __future__ import annotations

import math

import polars as pl

from ditto_analytics.evaluation.report import LongShortResult, TailRiskMetrics

from ._math import scalar_to_float
from .tail_risk import tail_risk_metrics

__all__ = [
    "long_short_returns",
    "net_returns",
    "quantile_returns",
    "turnover",
    "turnover_adjusted_ir",
]


# ---------------------------------------------------------------------------
# Quantile portfolio returns
# ---------------------------------------------------------------------------


def quantile_returns(
    factor_df: pl.DataFrame,
    return_df: pl.DataFrame,
    *,
    n_quantiles: int = 5,
    factor_col: str = "value",
    return_col: str = "forward_return",
    date_col: str = "trade_date",
    entity_col: str = "instrument_id",
) -> pl.DataFrame:
    """
    Equal-frequency quantile portfolio returns.

    Within each date, rank factor values into *n_quantiles* groups using
    :meth:`pl.Expr.qcut <polars.Expr.qcut>` and compute the mean return
    per group.

    Args:
        factor_df: DataFrame with factor values.
        return_df: DataFrame with forward returns.
        n_quantiles: Number of equal-frequency quantile groups.
        factor_col: Name of the factor value column.
        return_col: Name of the forward return column.
        date_col: Name of the date column.
        entity_col: Name of the entity identifier column.

    Returns:
        ``pl.DataFrame[date, quantile, mean_return, count]`` sorted by
        ``(date, quantile)``.

    """
    joined = factor_df.join(
        return_df,
        on=[date_col, entity_col],
        how="inner",
    )
    result = (
        joined.with_columns(
            quantile=pl.col(factor_col).qcut(
                n_quantiles,
                labels=[str(i + 1) for i in range(n_quantiles)],
            ),
        )
        .group_by(date_col, "quantile")
        .agg(
            mean_return=pl.col(return_col).mean(),
            count=pl.len(),
        )
        .sort(date_col, "quantile")
        .with_columns(quantile=pl.col("quantile").cast(pl.String).cast(pl.Int64))
    )
    return result


# ---------------------------------------------------------------------------
# Long-short portfolio analysis
# ---------------------------------------------------------------------------


def long_short_returns(
    quantile_ret_df: pl.DataFrame,
    *,
    quantile_col: str = "quantile",
    return_col: str = "mean_return",
    top_quantile: int = 5,
    bottom_quantile: int = 1,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 244,
) -> LongShortResult:
    """
    Compute long-short portfolio risk metrics.

    Daily LS returns = top-quantile mean return - bottom-quantile mean return.

    Metrics: annualised return (net of risk-free rate), annualised volatility,
    Sharpe ratio, Portfolio IR, Sortino ratio, maximum drawdown, Calmar ratio,
    and tail risk metrics.

    Args:
        quantile_ret_df: Output of :func:`quantile_returns`.
        quantile_col: Name of the quantile column.
        return_col: Name of the mean return column.
        top_quantile: Quantile number to go long.
        bottom_quantile: Quantile number to go short.
        risk_free_rate: Annualised risk-free rate.
        periods_per_year: Number of trading periods per year.

    Returns:
        A :class:`~ditto_analytics.evaluation.report.LongShortResult`.

    """
    top_df = quantile_ret_df.filter(pl.col(quantile_col) == top_quantile).sort(
        "trade_date"
    )
    bottom_df = quantile_ret_df.filter(pl.col(quantile_col) == bottom_quantile).sort(
        "trade_date"
    )

    empty_tail = TailRiskMetrics(
        cvar_95=0.0,
        cvar_99=0.0,
        skewness=0.0,
        kurtosis=0.0,
        max_single_day_loss=0.0,
    )
    empty_result = LongShortResult(
        annual_return=0.0,
        annual_volatility=0.0,
        sharpe=0.0,
        portfolio_ir=0.0,
        sortino=0.0,
        max_drawdown=0.0,
        calmar=0.0,
        tail_risk=empty_tail,
    )

    if top_df.height == 0 or bottom_df.height == 0:
        return empty_result

    # Align by row position (both sorted by date).
    ls_daily = top_df[return_col] - bottom_df[return_col]
    n = len(ls_daily)
    if n == 0:
        return empty_result

    # Subtract daily risk-free rate BEFORE annualizing.
    daily_rf = risk_free_rate / periods_per_year
    ls_daily_adjusted = ls_daily - daily_rf

    mean_daily = scalar_to_float(ls_daily_adjusted.mean())
    std_daily = scalar_to_float(ls_daily_adjusted.std(ddof=1) if n > 1 else None)

    annual_return = mean_daily * periods_per_year
    annual_vol = std_daily * math.sqrt(periods_per_year)

    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    # portfolio_ir is now the same as sharpe since rf is already subtracted.
    portfolio_ir = sharpe

    # Sortino — downside deviation only (using adjusted returns).
    negative = ls_daily_adjusted.filter(ls_daily_adjusted < 0)
    neg_std = scalar_to_float(
        negative.std(ddof=1) if len(negative) > 1 else None,
    )
    downside_std = neg_std * math.sqrt(periods_per_year)
    sortino = annual_return / downside_std if downside_std > 0 else 0.0

    # Max drawdown.
    cumulative = (1 + ls_daily).cum_prod()
    running_max = cumulative.cum_max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = scalar_to_float(drawdown.min())

    # Calmar ratio.
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    # Tail risk metrics.
    tr = tail_risk_metrics(ls_daily)

    return LongShortResult(
        annual_return=annual_return,
        annual_volatility=annual_vol,
        sharpe=sharpe,
        portfolio_ir=portfolio_ir,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
        tail_risk=tr,
    )


# ---------------------------------------------------------------------------
# Turnover-adjusted IR
# ---------------------------------------------------------------------------


def turnover_adjusted_ir(
    mean_ic: float,
    ic_autocorr_lag1: float,
    rebalance_freq: int = 5,
    total_periods: int = 244,
) -> float:
    """
    Turnover-adjusted IR correcting the Fundamental Law for IC autocorrelation.

    Formula (Gordon Ritter, IAQF):

    ``IR_adj = IC * sqrt(BR_effective)``

    where ``BR = total_periods / rebalance_freq`` and

    ``BR_effective = BR * (1 - rho^2) / (1 - 2*rho*cos(pi/T) + rho^2)``

    with ``rho = ic_autocorr_lag1`` and ``T = rebalance_freq``.

    Args:
        mean_ic: Mean IC (IC1).
        ic_autocorr_lag1: IC autocorrelation at lag 1.
        rebalance_freq: Rebalancing frequency in days.
        total_periods: Total number of periods per year.

    Returns:
        Turnover-adjusted information ratio.

    """
    br = total_periods / rebalance_freq
    rho = ic_autocorr_lag1
    t = rebalance_freq
    denominator = 1 - 2 * rho * math.cos(math.pi / t) + rho * rho
    if denominator <= 0:
        return 0.0
    br_effective = br * (1 - rho * rho) / denominator
    if br_effective <= 0:
        return 0.0
    return mean_ic * math.sqrt(br_effective)


# ---------------------------------------------------------------------------
# Turnover
# ---------------------------------------------------------------------------


def turnover(
    current_weights: pl.DataFrame,
    previous_weights: pl.DataFrame,
    *,
    entity_col: str = "instrument_id",
    weight_col: str = "weight",
    date_col: str = "trade_date",
) -> pl.DataFrame:
    """
    Compute one-way and two-way portfolio turnover.

    Two-way turnover = ``0.5 * sum(|w_t - w_{t-1}|)``.
    One-way turnover = ``min(buys, sells)`` where buys and sells are the
    positive and negative parts of ``w_t - w_{t-1}``.

    Args:
        current_weights: ``pl.DataFrame[date, entity, weight]`` for period *t*.
        previous_weights: ``pl.DataFrame[date, entity, weight]`` for period
            *t-1*.
        entity_col: Name of the entity column.
        weight_col: Name of the weight column.
        date_col: Name of the date column.

    Returns:
        ``pl.DataFrame[date, turnover_two_way, turnover_one_way]``.

    """
    joined = current_weights.join(
        previous_weights,
        on=[date_col, entity_col],
        how="inner",
        suffix="_prev",
    )
    diff_col = pl.col(weight_col) - pl.col(f"{weight_col}_prev")
    result = (
        joined.with_columns(diff=diff_col)
        .group_by(date_col)
        .agg(
            turnover_two_way=0.5 * pl.col("diff").abs().sum(),
            buys=pl.col("diff").filter(pl.col("diff") > 0).sum(),
            sells=pl.col("diff").filter(pl.col("diff") < 0).abs().sum(),
        )
        .with_columns(
            turnover_one_way=pl.min_horizontal("buys", "sells"),
        )
        .drop("buys", "sells")
        .sort(date_col)
    )
    return result


# ---------------------------------------------------------------------------
# Net returns
# ---------------------------------------------------------------------------


def net_returns(
    gross_return: float,
    avg_turnover: float,
    cost_bps: float = 20.0,
) -> float:
    """
    Net return after transaction costs.

    ``net = gross - avg_turnover * cost_bps / 10000``

    Args:
        gross_return: Annualised gross return.
        avg_turnover: Average two-way turnover.
        cost_bps: Transaction cost in basis points.

    Returns:
        Net return after costs.

    """
    return gross_return - avg_turnover * cost_bps / 10000.0
