"""
Factor evaluation metrics — pure Polars vectorized computations.

All functions are stateless, side-effect free, and depend only on ``polars``
and the standard library.  They accept / return ``pl.DataFrame`` or simple
Python containers.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import polars as pl
from polars._typing import PythonLiteral

from ditto_core.engine.evaluation.report import (
    ICSummary,
    LongShortResult,
    TailRiskMetrics,
)

__all__ = [
    "grinold_kahn_ir",
    "ic_autocorrelation",
    "ic_decay",
    "ic_summary",
    "long_short_returns",
    "net_returns",
    "orthogonalize",
    "pearson_ic",
    "quantile_returns",
    "rank_ic",
    "sub_period_ic",
    "tail_risk_metrics",
    "turnover",
    "turnover_adjusted_ir",
]

# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------


def rank_ic(
    factor_df: pl.DataFrame,
    return_df: pl.DataFrame,
    *,
    factor_col: str = "value",
    return_col: str = "forward_return",
    date_col: str = "trade_date",
    entity_col: str = "instrument_id",
) -> pl.DataFrame:
    """
    Compute daily Spearman Rank IC.

    Join *factor_df* and *return_df* on ``(date, entity)``, then compute the
    Spearman rank correlation per date.

    Args:
        factor_df: DataFrame with factor values (date, entity, factor_col).
        return_df: DataFrame with forward returns (date, entity, return_col).
        factor_col: Name of the factor value column.
        return_col: Name of the forward return column.
        date_col: Name of the date column.
        entity_col: Name of the entity identifier column.

    Returns:
        ``pl.DataFrame[date, ic]`` sorted ascending by date.

    """
    joined = factor_df.join(
        return_df,
        on=[date_col, entity_col],
        how="inner",
    )
    result = (
        joined.group_by(date_col)
        .agg(
            ic=pl.corr(
                pl.col(factor_col),
                pl.col(return_col),
                method="spearman",
            ),
        )
        .sort(date_col)
    )
    return result


def pearson_ic(
    factor_df: pl.DataFrame,
    return_df: pl.DataFrame,
    *,
    factor_col: str = "value",
    return_col: str = "forward_return",
    date_col: str = "trade_date",
    entity_col: str = "instrument_id",
) -> pl.DataFrame:
    """
    Compute daily Pearson IC.

    Join *factor_df* and *return_df* on ``(date, entity)``, then compute the
    Pearson correlation per date.

    Args:
        factor_df: DataFrame with factor values.
        return_df: DataFrame with forward returns.
        factor_col: Name of the factor value column.
        return_col: Name of the forward return column.
        date_col: Name of the date column.
        entity_col: Name of the entity identifier column.

    Returns:
        ``pl.DataFrame[date, ic]`` sorted ascending by date.

    """
    joined = factor_df.join(
        return_df,
        on=[date_col, entity_col],
        how="inner",
    )
    result = (
        joined.group_by(date_col)
        .agg(
            ic=pl.corr(
                pl.col(factor_col),
                pl.col(return_col),
                method="pearson",
            ),
        )
        .sort(date_col)
    )
    return result


# ---------------------------------------------------------------------------
# IC summary statistics
# ---------------------------------------------------------------------------


def ic_summary(
    ic_df: pl.DataFrame,
    *,
    ic_col: str = "ic",
    date_col: str = "trade_date",
) -> ICSummary:
    """
    Compute IC time-series statistical summary.

    Includes mean, std, ICIR (mean/std), one-sample t-statistic with
    two-sided *p*-value, and win rate (proportion of days with IC > 0).

    Args:
        ic_df: ``pl.DataFrame[date, ic]`` produced by :func:`rank_ic` or
            :func:`pearson_ic`.
        ic_col: Name of the IC column.
        date_col: Name of the date column.

    Returns:
        An :class:`~ditto_core.engine.evaluation.report.ICSummary` instance.

    """
    clean = (
        ic_df.select(pl.col(ic_col)).drop_nulls().filter(pl.col(ic_col).is_not_nan())
    )
    n = clean.height
    if n == 0:
        return ICSummary(
            mean=0.0,
            std=0.0,
            icir=0.0,
            t_stat=0.0,
            p_value=1.0,
            win_rate=0.0,
        )

    ic_vals = clean.to_series()
    mean_val = _scalar_to_float(ic_vals.mean())
    std_raw = ic_vals.std(ddof=1)
    std_val = _scalar_to_float(std_raw)

    if std_val == 0.0 or not math.isfinite(std_val):
        win_rate = _scalar_to_float((ic_vals > 0).mean())
        return ICSummary(
            mean=mean_val,
            std=std_val,
            icir=0.0,
            t_stat=0.0,
            p_value=1.0,
            win_rate=win_rate,
        )

    icir = mean_val / std_val
    t_stat = mean_val / (std_val / math.sqrt(n))
    # Two-sided p-value from t-distribution with n-1 degrees of freedom.
    p_value = _two_sided_p_value(t_stat, n - 1)
    win_rate = _scalar_to_float((ic_vals > 0).mean())

    return ICSummary(
        mean=mean_val,
        std=std_val,
        icir=icir,
        t_stat=t_stat,
        p_value=p_value,
        win_rate=win_rate,
    )


# ---------------------------------------------------------------------------
# IC decay and autocorrelation
# ---------------------------------------------------------------------------


def ic_decay(
    factor_df: pl.DataFrame,
    close_df: pl.DataFrame,
    *,
    lags: list[int] | None = None,
    factor_col: str = "value",
    date_col: str = "trade_date",
    entity_col: str = "instrument_id",
) -> tuple[list[tuple[int, float]], float | None]:
    """
    Compute Rank IC at various forward lags and fit IC half-life.

    For each *lag*, forward returns are derived from *close_df* and then
    :func:`rank_ic` is invoked.  The IC half-life is estimated by fitting
    ``IC(lag) = A * exp(-lag / half_life)`` using least-squares on
    ``log(IC^2)`` vs *lag*.

    Args:
        factor_df: DataFrame with factor values.
        close_df: DataFrame with ``[date, entity, close]`` prices.
        lags: Forward return lags.  Defaults to ``[1, 2, 3, 5, 10, 20]``.
        factor_col: Name of the factor value column.
        date_col: Name of the date column.
        entity_col: Name of the entity identifier column.

    Returns:
        ``(decay_results, half_life)`` where *decay_results* is
        ``[(lag, mean_ic), ...]`` and *half_life* is ``None`` when the fit
        fails.

    """
    if lags is None:
        lags = [1, 2, 3, 5, 10, 20]

    close_sorted = close_df.sort([entity_col, date_col])

    decay_results: list[tuple[int, float]] = []
    for lag in lags:
        return_df = (
            close_sorted.group_by(entity_col, maintain_order=True)
            .agg(
                forward_return=pl.col("close").pct_change(lag).shift(-lag),
            )
            .explode("forward_return")
            .select(
                pl.col(entity_col),
                trade_date=pl.lit(None).cast(close_df[date_col].dtype),
                forward_return=pl.col("forward_return"),
            )
        )
        # Re-attach dates via a windowed join approach.
        return_df = _attach_dates(close_sorted, return_df, entity_col, date_col)

        ic_df = rank_ic(
            factor_df,
            return_df,
            factor_col=factor_col,
            return_col="forward_return",
            date_col=date_col,
            entity_col=entity_col,
        )
        ic_mean = ic_df.select(pl.col("ic").drop_nulls().mean()).item()
        mean_ic_val = _scalar_to_float(ic_mean)
        decay_results.append((lag, mean_ic_val))

    half_life = _fit_ic_half_life(decay_results)
    return decay_results, half_life


def ic_autocorrelation(
    ic_df: pl.DataFrame,
    *,
    max_lag: int = 10,
    ic_col: str = "ic",
) -> list[tuple[int, float]]:
    """
    IC autocorrelation function (ACF).

    Compute the Pearson correlation between ``ic[t]`` and ``ic[t - lag]``
    for *lag* = 1 .. *max_lag*.

    Args:
        ic_df: ``pl.DataFrame[date, ic]`` sorted by date.
        max_lag: Maximum lag to compute.
        ic_col: Name of the IC column.

    Returns:
        ``[(lag, acf_value), ...]`` for lag 1..max_lag.

    """
    series = ic_df.select(pl.col(ic_col)).drop_nulls().to_series()
    n = len(series)
    result: list[tuple[int, float]] = []

    for lag in range(1, max_lag + 1):
        if lag >= n:
            result.append((lag, float("nan")))
            continue
        x = series.slice(lag)
        y = series.slice(0, n - lag)
        # Pearson correlation via manual computation.
        x_mean = x.mean()
        y_mean = y.mean()
        dx = x - x_mean
        dy = y - y_mean
        num = float((dx * dy).sum())
        den = math.sqrt(float((dx * dx).sum()) * float((dy * dy).sum()))
        acf = num / den if den != 0 else float("nan")
        result.append((lag, acf))

    return result


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
        A :class:`~ditto_core.engine.evaluation.report.LongShortResult`.

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

    mean_daily = _scalar_to_float(ls_daily_adjusted.mean())
    std_daily = _scalar_to_float(ls_daily.std(ddof=1) if n > 1 else None)

    annual_return = mean_daily * periods_per_year
    annual_vol = std_daily * math.sqrt(periods_per_year)

    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    # portfolio_ir is now the same as sharpe since rf is already subtracted.
    portfolio_ir = sharpe

    # Sortino — downside deviation only (using adjusted returns).
    negative = ls_daily_adjusted.filter(ls_daily_adjusted < 0)
    neg_std = _scalar_to_float(
        negative.std(ddof=1) if len(negative) > 1 else None,
    )
    downside_std = neg_std * math.sqrt(periods_per_year)
    sortino = annual_return / downside_std if downside_std > 0 else 0.0

    # Max drawdown.
    cumulative = (1 + ls_daily).cum_prod()
    running_max = cumulative.cum_max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = _scalar_to_float(drawdown.min())

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
# Tail risk metrics
# ---------------------------------------------------------------------------


def tail_risk_metrics(ls_daily: pl.Series) -> TailRiskMetrics:
    """
    Compute tail risk statistics from a daily long-short returns series.

    Args:
        ls_daily: Daily long-short returns as a Polars Series.

    Returns:
        A :class:`~ditto_core.engine.evaluation.report.TailRiskMetrics` instance.
        Returns all zeros if the series is empty or has fewer than 2 elements.

    """
    n = len(ls_daily)
    _MIN_TAIL_OBSERVATIONS = 2
    if n < _MIN_TAIL_OBSERVATIONS:
        return TailRiskMetrics(
            cvar_95=0.0,
            cvar_99=0.0,
            skewness=0.0,
            kurtosis=0.0,
            max_single_day_loss=_scalar_to_float(ls_daily.min()) if n == 1 else 0.0,
        )

    sorted_vals = ls_daily.sort()

    # CVaR 95%: mean of worst 5%.
    cutoff_95 = max(1, math.ceil(n * 0.05))
    worst_95 = sorted_vals.slice(0, cutoff_95)
    cvar_95 = _scalar_to_float(worst_95.mean())

    # CVaR 99%: mean of worst 1%.
    cutoff_99 = max(1, math.ceil(n * 0.01))
    worst_99 = sorted_vals.slice(0, cutoff_99)
    cvar_99 = _scalar_to_float(worst_99.mean())

    # Skewness and excess kurtosis.
    skewness = _scalar_to_float(ls_daily.skew())
    kurtosis = _scalar_to_float(ls_daily.kurtosis()) - 3.0

    # Max single day loss.
    max_single_day_loss = _scalar_to_float(ls_daily.min())

    return TailRiskMetrics(
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        skewness=skewness,
        kurtosis=kurtosis,
        max_single_day_loss=max_single_day_loss,
    )


# ---------------------------------------------------------------------------
# Grinold-Kahn IR
# ---------------------------------------------------------------------------


def grinold_kahn_ir(
    mean_ic: float,
    ic_std: float,
    ic_autocorr_lag1: float,
    breadth: float,
    rebalance_freq: int = 5,
    periods_per_year: int = 244,
) -> float:
    """
    Compute the Grinold-Kahn Information Ratio using the Fundamental Law.

    ``IR = IC * sqrt(BR_effective)``

    where ``IC = mean_ic / ic_std`` and ``BR_effective`` is computed using
    the Gordon Ritter autocorrelation correction:

    ``BR_effective = BR * (1 - rho^2) / (1 - 2*rho*cos(pi/T) + rho^2)``

    with ``rho = ic_autocorr_lag1`` and ``T = periods_per_year``.

    Args:
        mean_ic: Mean IC value.
        ic_std: IC standard deviation.
        ic_autocorr_lag1: IC autocorrelation at lag 1.
        breadth: Strategy breadth (e.g. n_dates * (n_quantiles - 1) / n_quantiles).
        rebalance_freq: Rebalancing frequency in days.
        periods_per_year: Number of periods per year.

    Returns:
        Grinold-Kahn IR. Returns 0.0 if ic_std is 0 or breadth is <= 0.

    """
    if ic_std == 0.0 or breadth <= 0:
        return 0.0

    ic_ratio = mean_ic / ic_std
    rho = ic_autocorr_lag1
    t_periods = periods_per_year

    denominator = 1 - 2 * rho * math.cos(math.pi / t_periods) + rho * rho
    if denominator <= 0:
        return 0.0

    br_effective = breadth * (1 - rho * rho) / denominator
    if br_effective <= 0:
        return 0.0

    return ic_ratio * math.sqrt(br_effective)


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


# ---------------------------------------------------------------------------
# Factor orthogonalization
# ---------------------------------------------------------------------------


def orthogonalize(
    target: pl.DataFrame,
    factors: pl.DataFrame,
    *,
    entity_col: str = "instrument_id",
    date_col: str = "trade_date",
    value_col: str = "value",
    method: str = "sequential",
    min_cross_section: int = 30,
) -> pl.DataFrame:
    """
    Factor orthogonalization via regression residuals.

    For each date cross-section with at least *min_cross_section*
    observations:

    * **sequential** — OLS residual of *target* on each factor one at a time
      (successive orthogonalisation).
    * **symmetric** — project out the first principal component of the factor
      matrix.

    Args:
        target: ``pl.DataFrame[date, entity, value]`` — factor to orthogonalise.
        factors: ``pl.DataFrame[date, entity, value]`` — control factors.
            Must contain a ``factor_name`` column to distinguish different
            factors.
        entity_col: Name of the entity column.
        date_col: Name of the date column.
        value_col: Name of the value column.
        method: ``"sequential"`` or ``"symmetric"``.
        min_cross_section: Minimum observations per date to compute.

    Returns:
        ``pl.DataFrame[date, entity, orthogonalized_value]`` sorted by
        ``(date, entity)``.

    """
    joined = target.join(
        factors,
        on=[date_col, entity_col],
        how="inner",
        suffix="_factor",
    )
    dates = joined.select(pl.col(date_col)).unique().sort(date_col)

    if method == "sequential":
        return _orthogonalize_sequential(
            joined,
            dates,
            date_col=date_col,
            entity_col=entity_col,
            min_cross_section=min_cross_section,
            value_col=value_col,
        )
    if method == "symmetric":
        return _orthogonalize_symmetric(
            joined,
            dates,
            date_col=date_col,
            entity_col=entity_col,
            min_cross_section=min_cross_section,
            value_col=value_col,
        )

    msg = f"Unknown orthogonalization method: {method!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Sub-period IC analysis
# ---------------------------------------------------------------------------


def sub_period_ic(
    ic_df: pl.DataFrame,
    *,
    ic_col: str = "ic",
    date_col: str = "trade_date",
    freq: str = "year",
) -> dict[str, ICSummary]:
    """
    Sub-period IC summary for stability analysis.

    Split the IC series by year or quarter, compute :func:`ic_summary` for
    each sub-period.

    Args:
        ic_df: ``pl.DataFrame[date, ic]`` sorted by date.
        ic_col: Name of the IC column.
        date_col: Name of the date column.
        freq: ``"year"`` or ``"quarter"``.

    Returns:
        ``{period_label: ICSummary}`` mapping, e.g. ``{"2024": ...}``.

    """
    df = ic_df.select(pl.col(date_col), pl.col(ic_col)).drop_nulls()

    if freq == "year":
        df = df.with_columns(period=pl.col(date_col).dt.year().cast(pl.String))
    elif freq == "quarter":
        df = df.with_columns(
            period=(
                pl.col(date_col).dt.year().cast(pl.String)
                + "Q"
                + pl.col(date_col).dt.quarter().cast(pl.String)
            ),
        )
    else:
        msg = f"Unknown frequency: {freq!r}; use 'year' or 'quarter'"
        raise ValueError(msg)

    results: dict[str, ICSummary] = {}
    for key, group_df in df.group_by("period"):
        period_label = str(key[0])
        sub_df = group_df.select(
            pl.col(date_col).alias("trade_date"),
            pl.col(ic_col).alias("ic"),
        )
        results[period_label] = ic_summary(sub_df)

    return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _scalar_to_float(
    value: PythonLiteral | None,
    default: float = 0.0,
) -> float:
    """
    Safely convert a polars scalar to float.

    Polars ``.mean()``, ``.std()``, ``.min()`` return ``PythonLiteral | None``
    which basedpyright cannot narrow.  This helper bridges that gap.
    """
    if value is None:
        return default
    if isinstance(value, (bool, int, float, Decimal)):
        return float(value)
    if isinstance(value, timedelta):
        return value.total_seconds()
    # date, datetime, time, str, bytes, list, np.ndarray — compute a float
    # representation, falling back to *default* on failure.
    result: float = default
    if isinstance(value, date) and not isinstance(value, datetime):
        result = float(value.toordinal())
    elif isinstance(value, datetime):
        result = float(value.timestamp())
    elif isinstance(value, time):
        result = float(value.hour * 3600 + value.minute * 60 + value.second)
    elif isinstance(value, (str, bytes)):
        try:
            result = float(value)
        except (TypeError, ValueError):
            pass
    # list / np.ndarray — not convertible to float; keep *default*.
    return result


def _two_sided_p_value(t: float, df: int) -> float:
    """
    Approximate two-sided p-value from the t-distribution.

    Uses the regularised incomplete beta function identity:

        p = I_x(a, b)  where x = df / (df + t^2), a = df/2, b = 1/2

    Args:
        t: t-statistic.
        df: Degrees of freedom.

    Returns:
        Two-sided p-value.

    """
    x = df / (df + t * t)
    return _regularized_incomplete_beta(x, df / 2.0, 0.5)


def _regularized_incomplete_beta(
    x: float,
    a: float,
    b: float,
    *,
    max_iter: int = 200,
    tol: float = 1e-12,
) -> float:
    """
    Compute the regularised incomplete beta function I_x(a, b).

    Uses the continued fraction expansion (Lentz's method) for numerical
    stability.  Falls back to the series expansion when the continued
    fraction does not converge.

    Args:
        x: Value in [0, 1].
        a: First shape parameter (> 0).
        b: Second shape parameter (> 0).
        max_iter: Maximum iterations for the continued fraction.
        tol: Convergence tolerance.

    Returns:
        I_x(a, b) in [0, 1].

    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    # Use log-gamma for numerical safety.
    log_prefix = (
        _log_gamma(a + b)
        - _log_gamma(a)
        - _log_gamma(b)
        + a * math.log(x)
        + b * math.log(1 - x)
    )
    prefix = math.exp(log_prefix)

    if x < (a + 1) / (a + b + 2):
        result = prefix * _beta_cf(x, a, b, max_iter=max_iter, tol=tol) / a
        return result
    result = 1.0 - prefix * _beta_cf(1 - x, b, a, max_iter=max_iter, tol=tol) / b
    return result


def _beta_cf(
    x: float,
    a: float,
    b: float,
    *,
    max_iter: int = 200,
    tol: float = 1e-12,
) -> float:
    """
    Evaluate the continued fraction for the incomplete beta function.

    Implements the modified Lentz method for the continued fraction:

        1 + d_1/(1 + d_2/(1 + ...))

    Args:
        x: Value in (0, 1).
        a: First shape parameter.
        b: Second shape parameter.
        max_iter: Maximum iterations.
        tol: Convergence tolerance.

    Returns:
        The continued fraction value.

    """
    tiny = 1e-30
    f = 1.0
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1)
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    f = d

    for m in range(1, max_iter + 1):
        numerator_m = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + numerator_m * d
        if abs(d) < tiny:
            d = tiny
        d = 1.0 / d
        c = 1.0 + numerator_m / c
        if abs(c) < tiny:
            c = tiny
        f *= c * d

        numerator_m2 = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + numerator_m2 * d
        if abs(d) < tiny:
            d = tiny
        d = 1.0 / d
        c = 1.0 + numerator_m2 / c
        if abs(c) < tiny:
            c = tiny
        delta = c * d
        f *= delta

        if abs(delta - 1.0) < tol:
            break

    return f


def _log_gamma(x: float) -> float:
    """
    Lanczos approximation of log(Gamma(x)) for x > 0.

    Uses the coefficients from Numerical Recipes (Press et al.) with g = 7.

    Args:
        x: Positive real number.

    Returns:
        ``log(Gamma(x))``.

    """
    if x <= 0:
        msg = f"log_gamma requires x > 0, got {x}"
        raise ValueError(msg)

    coefs = [
        0.99999999999980993,
        676.5203681218851,
        -1259.1392167224028,
        771.32342877765313,
        -176.61502916214059,
        12.507343278686905,
        -0.13857109526572012,
        9.9843695780195716e-6,
        1.5056327351493116e-7,
    ]
    g = 7
    reflection_threshold = 0.5
    if x < reflection_threshold:
        # Reflection formula: Gamma(x) * Gamma(1-x) = pi / sin(pi*x)
        return math.log(math.pi / math.sin(math.pi * x)) - _log_gamma(1 - x)

    x -= 1.0
    a = coefs[0]
    t = x + g + 0.5
    for i in range(1, len(coefs)):
        a += coefs[i] / (x + i)
    return 0.5 * math.log(2 * math.pi) + (x + 0.5) * math.log(t) - t + math.log(a)


def _fit_ic_half_life(
    decay_results: list[tuple[int, float]],
) -> float | None:
    """
    Fit IC half-life via least-squares on log(IC^2) vs lag.

    Model: ``IC(lag) = A * exp(-lag / half_life)``
    Linearised: ``log(IC^2) = log(A^2) - 2*lag / half_life``

    Args:
        decay_results: ``[(lag, mean_ic), ...]`` with positive mean_ic.

    Returns:
        Estimated half-life in days, or ``None`` if the fit is not possible.

    """
    MIN_POINTS_FOR_FIT = 2
    valid = [(lag, ic) for lag, ic in decay_results if ic > 0]
    if len(valid) < MIN_POINTS_FOR_FIT:
        return None

    lags = [float(lag) for lag, _ in valid]
    log_ic2 = [math.log(ic * ic) for _, ic in valid]
    n = len(lags)
    sum_x = sum(lags)
    sum_y = sum(log_ic2)
    sum_xy = sum(x * y for x, y in zip(lags, log_ic2, strict=True))
    sum_x2 = sum(x * x for x in lags)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    # slope = -2 / half_life  =>  half_life = -2 / slope
    if slope >= 0:
        return None  # IC should decay, not grow.

    half_life = -2.0 / slope
    return half_life if half_life > 0 else None


def _attach_dates(
    close_sorted: pl.DataFrame,
    return_df: pl.DataFrame,
    entity_col: str,
    date_col: str,
) -> pl.DataFrame:
    """
    Re-attach dates to exploded return DataFrame.

    The return_df from group_by/explode loses the date context.  We reconstruct
    it by sorting close_sorted and joining on row index within each entity
    group.

    """
    close_with_idx = close_sorted.with_columns(
        row_idx=pl.arange(1, pl.len() + 1).over(entity_col),
    )
    # return_df has a row per entity per lag-offset.  We need to map each
    # row back to its original date.  The return at row_idx = i corresponds
    # to close[i] -> close[i+lag], so the "trade_date" is close's date at
    # row i.  After pct_change(lag).shift(-lag), the exploded index aligns
    # with the original rows 0..n-lag-1.
    return_df = return_df.with_columns(
        row_idx=pl.arange(1, pl.len() + 1).over(entity_col),
    )
    return return_df.join(
        close_with_idx.select(entity_col, "row_idx", date_col),
        on=[entity_col, "row_idx"],
        how="left",
    ).drop("row_idx")


def _orthogonalize_sequential(
    joined: pl.DataFrame,
    dates: pl.DataFrame,
    *,
    date_col: str,
    entity_col: str,
    min_cross_section: int,
    value_col: str = "value",
) -> pl.DataFrame:
    """Sequential OLS orthogonalization -- one factor at a time."""
    target_col = value_col
    factor_val_col = f"{value_col}_factor"
    factor_name_col = "factor_name"

    frames: list[pl.DataFrame] = []
    for date_row in dates.iter_rows(named=True):
        dt = date_row[date_col]
        cross = joined.filter(pl.col(date_col) == dt)
        if cross.height < min_cross_section:
            continue

        factor_names = cross[factor_name_col].unique(maintain_order=True).to_list()

        for fname in factor_names:
            sub = cross.filter(pl.col(factor_name_col) == fname)
            x_vals = sub[factor_val_col].to_numpy()
            target_sub = sub[target_col].to_numpy()

            # Simple OLS: residual = y - x * (x'x)^{-1} x'y
            xtx = float(x_vals @ x_vals)
            if xtx == 0:
                continue
            xty = float(x_vals @ target_sub)
            beta = xty / xtx
            residual_sub = target_sub - beta * x_vals

            # Map residuals back to the full cross-section.
            cross = cross.with_columns(
                pl.lit(residual_sub).alias(target_col),
            )

        frame = cross.select(
            pl.lit(dt).alias(date_col),
            pl.col(entity_col),
            orthogonalized_value=pl.col(target_col),
        )
        frames.append(frame)

    if not frames:
        return pl.DataFrame(
            schema={
                date_col: joined[date_col].dtype,
                entity_col: joined[entity_col].dtype,
                "orthogonalized_value": pl.Float64,
            },
        )

    return pl.concat(frames).sort(date_col, entity_col)


def _orthogonalize_symmetric(
    joined: pl.DataFrame,
    dates: pl.DataFrame,
    *,
    date_col: str,
    entity_col: str,
    min_cross_section: int,
    value_col: str = "value",
) -> pl.DataFrame:
    """Symmetric orthogonalization via first principal component removal."""
    target_col = value_col
    factor_val_col = f"{value_col}_factor"
    factor_name_col = "factor_name"

    frames: list[pl.DataFrame] = []
    for date_row in dates.iter_rows(named=True):
        dt = date_row[date_col]
        cross = joined.filter(pl.col(date_col) == dt)
        if cross.height < min_cross_section:
            continue

        # Get unique entities (one row per entity in the target).
        target_unique = cross.select(entity_col, target_col).unique(
            subset=entity_col,
            maintain_order=True,
        )
        if target_unique.height < min_cross_section:
            continue

        entity_order = target_unique[entity_col].to_list()
        target_vals = target_unique[target_col].to_list()
        n = len(entity_order)

        factor_names = cross[factor_name_col].unique(maintain_order=True).to_list()
        if not factor_names:
            continue

        f_matrix = _build_factor_matrix(
            cross,
            factor_names,
            entity_order,
            entity_col,
            factor_name_col,
            factor_val_col,
        )

        residuals = _remove_first_pc(target_vals, f_matrix)

        frame = pl.DataFrame(
            {
                date_col: [dt] * n,
                entity_col: entity_order,
                "orthogonalized_value": residuals,
            },
        )
        frames.append(frame)

    if not frames:
        return pl.DataFrame(
            schema={
                date_col: joined[date_col].dtype,
                entity_col: joined[entity_col].dtype,
                "orthogonalized_value": pl.Float64,
            },
        )

    return pl.concat(frames).sort(date_col, entity_col)


def _build_factor_matrix(
    cross: pl.DataFrame,
    factor_names: list[str],
    entity_order: list[int],
    entity_col: str,
    factor_name_col: str,
    factor_val_col: str,
) -> list[list[float]]:
    """Build an (n_entities x n_factors) matrix from the cross-section data."""
    entity_factor_map: dict[tuple[str, int], float] = {}
    for row in cross.iter_rows(named=True):
        eid = row[entity_col]
        fname = row[factor_name_col]
        entity_factor_map[(fname, eid)] = row[factor_val_col]

    return [
        [entity_factor_map.get((fname, eid), 0.0) for eid in entity_order]
        for fname in factor_names
    ]


def _remove_first_pc(
    target_vals: list[float],
    f_matrix: list[list[float]],
    *,
    max_iter: int = 100,
) -> list[float]:
    """
    Remove the first principal component from *target_vals*.

    Uses power iteration on F'F/n to find the dominant eigenvector of the
    factor covariance matrix, projects the target onto it, and subtracts.
    """
    n = len(target_vals)
    k = len(f_matrix)

    cov = _covariance_matrix(f_matrix, n, k)
    v = _dominant_eigenvector(cov, k, max_iter=max_iter)

    # First PC in entity-space: pc1 = F @ v.
    pc1 = [sum(f_matrix[j][r] * v[j] for j in range(k)) for r in range(n)]
    pc1_norm = math.sqrt(sum(x * x for x in pc1))
    if pc1_norm > 0:
        pc1 = [x / pc1_norm for x in pc1]

    projection = sum(target_vals[r] * pc1[r] for r in range(n))
    return [target_vals[r] - projection * pc1[r] for r in range(n)]


def _covariance_matrix(
    f_matrix: list[list[float]],
    n: int,
    k: int,
) -> list[list[float]]:
    """Compute C = F'F / n (k x k)."""
    return [
        [sum(f_matrix[i][r] * f_matrix[j][r] for r in range(n)) / n for j in range(k)]
        for i in range(k)
    ]


def _dominant_eigenvector(
    cov: list[list[float]],
    k: int,
    *,
    max_iter: int = 100,
) -> list[float]:
    """Find the dominant eigenvector via power iteration."""
    CONVERGENCE_TOL = 1e-15
    v = [1.0 / math.sqrt(k)] * k
    for _ in range(max_iter):
        new_v = [sum(cov[i][j] * v[j] for j in range(k)) for i in range(k)]
        norm = math.sqrt(sum(x * x for x in new_v))
        if norm < CONVERGENCE_TOL:
            break
        v = [x / norm for x in new_v]
    return v
