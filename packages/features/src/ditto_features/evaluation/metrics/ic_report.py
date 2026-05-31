"""IC report generation and advanced analysis."""

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
    scalar_to_float,
    two_sided_p_value,
)
from .ic_computation import ic_summary

__all__ = [
    "ic_momentum",
    "regime_adjusted_ic",
    "sub_period_ic",
]


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
