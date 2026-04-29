"""Performance attribution decomposition."""

from __future__ import annotations

import math

import polars as pl

from ditto_analytics.evaluation.report import PerformanceAttributionResult

from ._math import IR_TE_EPSILON, scalar_to_float

__all__ = ["performance_attribution"]


def performance_attribution(
    quantile_ret_df: pl.DataFrame,
    *,
    periods_per_year: int = 244,
    quantile_col: str = "quantile",
    return_col: str = "mean_return",
    date_col: str = "trade_date",
) -> PerformanceAttributionResult:
    """
    Decompose factor portfolio performance into selection, timing, interaction.

    * **total_return**: Annualized equal-weighted average of all quantile returns.
    * **selection_return**: Annualized long-short spread (top - bottom).
    * **timing_return**: ``total_return - selection_return`` (simplified model).
    * **interaction_return**: 0.0 (simplified decomposition).
    * **annual_alpha**: Same as selection_return.
    * **tracking_error**: Daily std of LS return * sqrt(periods_per_year).
    * **information_ratio**: alpha / tracking_error (0.0 if TE is 0).

    Args:
        quantile_ret_df: ``pl.DataFrame[date, quantile, mean_return]``.
        periods_per_year: Trading periods per year for annualisation.
        quantile_col: Name of the quantile column.
        return_col: Name of the mean return column.
        date_col: Name of the date column.

    Returns:
        A :class:`~ditto_analytics.evaluation.report.PerformanceAttributionResult`.

    """
    if quantile_ret_df.height == 0:
        return PerformanceAttributionResult(
            total_return=0.0,
            selection_return=0.0,
            timing_return=0.0,
            interaction_return=0.0,
            annual_alpha=0.0,
            tracking_error=0.0,
            information_ratio=0.0,
            win_rate_by_quantile={},
        )

    # Total return: equal-weighted average across all quantiles, annualized
    total_daily = scalar_to_float(
        quantile_ret_df.select(pl.col(return_col).mean()).item(),
    )
    total_return = total_daily * periods_per_year

    # Selection return: LS spread (top quantile - bottom quantile), annualized
    max_q = scalar_to_float(
        quantile_ret_df.select(pl.col(quantile_col).max()).item(),
    )
    min_q = scalar_to_float(
        quantile_ret_df.select(pl.col(quantile_col).min()).item(),
    )

    top_daily = scalar_to_float(
        quantile_ret_df.filter(pl.col(quantile_col) == max_q)
        .select(pl.col(return_col).mean())
        .item(),
    )
    bottom_daily = scalar_to_float(
        quantile_ret_df.filter(pl.col(quantile_col) == min_q)
        .select(pl.col(return_col).mean())
        .item(),
    )
    ls_daily = top_daily - bottom_daily
    selection_return = ls_daily * periods_per_year

    # Timing and interaction (simplified)
    timing_return = total_return - selection_return
    interaction_return = 0.0

    # Alpha = selection return
    annual_alpha = selection_return

    # Tracking error: std of daily LS returns * sqrt(periods_per_year)
    # Compute daily LS spread per date
    dates = quantile_ret_df.select(pl.col(date_col).unique()).sort(date_col)
    ls_series = dates.join(
        quantile_ret_df.filter(pl.col(quantile_col) == max_q).select(
            pl.col(date_col),
            pl.col(return_col).alias("top_ret"),
        ),
        on=date_col,
        how="left",
    ).join(
        quantile_ret_df.filter(pl.col(quantile_col) == min_q).select(
            pl.col(date_col),
            pl.col(return_col).alias("bottom_ret"),
        ),
        on=date_col,
        how="left",
    )
    ls_series = ls_series.with_columns(
        ls=pl.col("top_ret") - pl.col("bottom_ret"),
    )

    ls_std = scalar_to_float(
        ls_series.select(pl.col("ls").std(ddof=1)).item(),
    )
    tracking_error = ls_std * math.sqrt(periods_per_year)

    # Information ratio
    information_ratio = (
        annual_alpha / tracking_error if tracking_error > IR_TE_EPSILON else 0.0
    )

    # Win rate by quantile
    win_rate_by_quantile: dict[int, float] = {}
    for q_val in quantile_ret_df.select(pl.col(quantile_col).unique()).to_series():
        q_df = quantile_ret_df.filter(pl.col(quantile_col) == q_val)
        n_positive = scalar_to_float(
            q_df.filter(pl.col(return_col) > 0).height,
        )
        n_total = q_df.height
        win_rate_by_quantile[int(q_val)] = n_positive / n_total if n_total > 0 else 0.0

    return PerformanceAttributionResult(
        total_return=total_return,
        selection_return=selection_return,
        timing_return=timing_return,
        interaction_return=interaction_return,
        annual_alpha=annual_alpha,
        tracking_error=tracking_error,
        information_ratio=information_ratio,
        win_rate_by_quantile=win_rate_by_quantile,
    )
