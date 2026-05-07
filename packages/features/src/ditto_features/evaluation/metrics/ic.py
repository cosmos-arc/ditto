"""IC (Information Coefficient) computation and analysis."""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from ditto_features.errors import EvaluationError
from ditto_features.evaluation.report import (
    ICSummary,
    RegimeICResult,
)

from ._math import (
    MIN_OBS_FOR_OLS,
    MIN_TRANSITIONS_FOR_MATRIX,
    fit_ic_half_life,
    scalar_to_float,
    two_sided_p_value,
)

__all__ = [
    "ic_autocorrelation",
    "ic_decay",
    "ic_momentum",
    "ic_summary",
    "pearson_ic",
    "rank_ic",
    "regime_adjusted_ic",
    "sub_period_ic",
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
        An :class:`~ditto_features.evaluation.report.ICSummary` instance.

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
    mean_val = scalar_to_float(ic_vals.mean())
    std_raw = ic_vals.std(ddof=1)
    std_val = scalar_to_float(std_raw)

    if std_val == 0.0 or not math.isfinite(std_val):
        win_rate = scalar_to_float((ic_vals > 0).mean())
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
    p_value = two_sided_p_value(t_stat, n - 1)
    win_rate = scalar_to_float((ic_vals > 0).mean())

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

    .. warning::
       此函数使用前向收益率（shift(-lag)），仅限离线因子评估使用。
       禁止用于任何实盘信号生成路径。

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
        mean_ic_val = scalar_to_float(ic_mean)
        decay_results.append((lag, mean_ic_val))

    half_life = fit_ic_half_life(decay_results)
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
        raise EvaluationError(
            f"Unknown frequency: {freq!r}; use 'year' or 'quarter'",
            field="freq",
            value=freq,
            supported=("year", "quarter"),
        )

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
# Regime-adjusted IC (EVAL-EV-5)
# ---------------------------------------------------------------------------


def regime_adjusted_ic(
    ic_df: pl.DataFrame,
    *,
    n_regimes: int = 2,
    ic_col: str = "ic",
    date_col: str = "trade_date",
) -> RegimeICResult:
    """
    Compute regime-switching IC analysis.

    Splits the IC series into regimes based on median of |IC|.  "low_vol"
    captures periods with |IC| <= median(|IC|), "high_vol" the rest.

    Args:
        ic_df: ``pl.DataFrame[date, ic]``.
        n_regimes: Number of regimes (only 2 is supported).
        ic_col: Name of the IC column.
        date_col: Name of the date column.

    Returns:
        A :class:`~ditto_features.evaluation.report.RegimeICResult`.

    """
    clean = (
        ic_df.select(pl.col(date_col), pl.col(ic_col))
        .drop_nulls(subset=[ic_col])
        .filter(pl.col(ic_col).is_not_nan())
        .sort(date_col)
    )

    if clean.height == 0:
        return RegimeICResult(
            regimes={},
            regime_labels=[],
            transition_matrix={},
            ic_trend=0.0,
            ic_trend_p_value=1.0,
        )

    ic_abs = clean.select(pl.col(ic_col).abs().alias("ic_abs"))
    median_abs = scalar_to_float(ic_abs.select(pl.col("ic_abs").median()).item())

    # Assign regime labels
    labeled = clean.with_columns(
        regime=pl.when(pl.col(ic_col).abs() <= median_abs)
        .then(pl.lit("low_vol"))
        .otherwise(pl.lit("high_vol"))
    )

    regime_labels: list[tuple[str, str]] = [
        (str(row[date_col]), row["regime"]) for row in labeled.iter_rows(named=True)
    ]

    # Compute IC summary per regime
    regimes: dict[str, ICSummary] = {}
    for regime_name in ("low_vol", "high_vol"):
        subset = labeled.filter(pl.col("regime") == regime_name)
        if subset.height > 0:
            regimes[regime_name] = ic_summary(subset, ic_col=ic_col, date_col=date_col)

    # Transition matrix
    transition_matrix = _build_transition_matrix(regime_labels)

    # IC trend
    ic_trend, ic_trend_p_value = ic_momentum(clean, ic_col=ic_col, date_col=date_col)

    return RegimeICResult(
        regimes=regimes,
        regime_labels=regime_labels,
        transition_matrix=transition_matrix,
        ic_trend=ic_trend,
        ic_trend_p_value=ic_trend_p_value,
    )


def _build_transition_matrix(
    labels: list[tuple[str, str]],
) -> dict[str, dict[str, float]]:
    """
    Build Markov transition matrix from consecutive regime labels.

    Args:
        labels: ``[(date_str, regime_name), ...]`` ordered by date.

    Returns:
        ``{from_regime: {to_regime: probability}}``.

    """
    if len(labels) < MIN_TRANSITIONS_FOR_MATRIX:
        return {}

    transitions: dict[tuple[str, str], int] = {}
    for i in range(1, len(labels)):
        from_r = labels[i - 1][1]
        to_r = labels[i][1]
        key = (from_r, to_r)
        transitions[key] = transitions.get(key, 0) + 1

    # Count outgoing transitions per regime
    from_counts: dict[str, int] = {}
    for (from_r, _to_r), count in transitions.items():
        from_counts[from_r] = from_counts.get(from_r, 0) + count

    # Build probability matrix
    result: dict[str, dict[str, float]] = {}
    all_regimes = sorted({r for _, r in labels})
    for from_r in all_regimes:
        result[from_r] = {}
        total = from_counts.get(from_r, 0)
        for to_r in all_regimes:
            count = transitions.get((from_r, to_r), 0)
            result[from_r][to_r] = count / total if total > 0 else 0.0

    return result


# ---------------------------------------------------------------------------
# IC momentum / trend (EVAL-EV-10)
# ---------------------------------------------------------------------------


def ic_momentum(
    ic_df: pl.DataFrame,
    *,
    window: int = 60,
    ic_col: str = "ic",
    date_col: str = "trade_date",
) -> tuple[float, float]:
    """
    Estimate IC trend via simple OLS on the last *window* IC values.

    Fits ``ic_t = alpha + beta * t`` and returns ``(beta, p_value)`` where
    *p_value* tests ``beta != 0``.

    For small samples (n <= 30), returns ``(0.0, 1.0)`` to avoid unreliable
    estimates.

    Args:
        ic_df: ``pl.DataFrame[date, ic]``.
        window: Number of trailing IC values to use.
        ic_col: Name of the IC column.
        date_col: Name of the date column.

    Returns:
        ``(trend_slope, p_value)``.

    """
    clean = (
        ic_df.select(pl.col(date_col), pl.col(ic_col))
        .drop_nulls(subset=[ic_col])
        .filter(pl.col(ic_col).is_not_nan())
        .sort(date_col)
        .tail(window)
    )

    n = clean.height
    if n <= MIN_OBS_FOR_OLS:
        return 0.0, 1.0

    ic_vals = clean.select(pl.col(ic_col)).to_series().to_numpy()
    t_vals = np.arange(n, dtype=np.float64)

    # OLS: beta = cov(t, ic) / var(t)
    t_mean = t_vals.mean()
    ic_mean = ic_vals.mean()
    cov_ti = np.sum((t_vals - t_mean) * (ic_vals - ic_mean)) / n
    var_t = np.sum((t_vals - t_mean) ** 2) / n

    if var_t == 0.0:
        return 0.0, 1.0

    beta = cov_ti / var_t
    residuals = ic_vals - (ic_mean + beta * (t_vals - t_mean))
    _ols_params = 2  # intercept + slope
    residual_var = np.sum(residuals**2) / (n - _ols_params) if n > _ols_params else 1.0

    # Standard error of beta
    se_beta = math.sqrt(residual_var / (n * var_t)) if residual_var > 0 else 0.0

    if se_beta == 0.0:
        return float(beta), 1.0

    t_stat = beta / se_beta
    p_value = two_sided_p_value(t_stat, n - 2)

    return float(beta), float(p_value)


# ---------------------------------------------------------------------------
# Private helpers (IC-specific)
# ---------------------------------------------------------------------------


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
    joined = return_df.join(
        close_with_idx.select(entity_col, "row_idx", date_col),
        on=[entity_col, "row_idx"],
        how="left",
    ).drop("row_idx")
    # The join may produce a suffixed date column (e.g. trade_date_right)
    # when return_df already has date_col.  Replace the null date_col with
    # the suffixed version.
    right_col = f"{date_col}_right"
    if right_col in joined.columns:
        joined = joined.drop(date_col).rename({right_col: date_col})
    return joined
