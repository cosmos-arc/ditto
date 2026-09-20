"""
Factor evaluation per-date series (IC, rolling IR, quantile, LS, monthly IC).

These derivations expose what the evaluator already computes internally
(``rank_ic`` per date, ``quantile_returns`` per date) before aggregation.
All functions are pure polars transformations over evaluation-grade frames.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = [
    "DEFAULT_ROLLING_IR_WINDOW",
    "FactorEvaluationSeries",
    "ls_nav_series",
    "monthly_ic",
    "quantile_nav_series",
    "rolling_ir_series",
]

DEFAULT_ROLLING_IR_WINDOW = 20
_MIN_ROLLING_WINDOW = 2


@dataclass(frozen=True, slots=True)
class FactorEvaluationSeries:
    """
    Per-date evaluation series sharing one trade-date axis.

    Attributes:
        period: Effective evaluation window ``(start, end)`` ISO dates.
        holding_period: Forward-return holding period (trading days).
        n_quantiles: Quantile group count.
        n_dates: Number of evaluation dates.
        ic: ``DataFrame[trade_date, ic]`` per-date Spearman rank IC.
        rolling_ir: ``DataFrame[trade_date, rolling_ir]``; null during warm-up.
        quantile_nav: ``DataFrame[trade_date, q_1..q_n]`` cumulative NAV per quantile.
        ls_nav: ``DataFrame[trade_date, ls_nav]`` cumulative long-short NAV.
        monthly_ic: ``DataFrame[year, month, mean_ic, days]``.

    """

    factor_id: str
    factor_version: int
    period: tuple[str, str]
    holding_period: int
    n_quantiles: int
    n_dates: int
    ic: pl.DataFrame
    rolling_ir: pl.DataFrame
    quantile_nav: pl.DataFrame
    ls_nav: pl.DataFrame
    monthly_ic: pl.DataFrame


def rolling_ir_series(
    ic_df: pl.DataFrame,
    *,
    window: int = DEFAULT_ROLLING_IR_WINDOW,
) -> pl.DataFrame:
    """Rolling mean(IC) / std(IC) over ``window`` dates; warm-up rows are null."""
    if window < _MIN_ROLLING_WINDOW:
        msg = f"rolling IR window must be >= {_MIN_ROLLING_WINDOW}, got {window}"
        raise ValueError(msg)
    return (
        ic_df.sort("trade_date")
        .with_columns(
            rolling_ir=pl.col("ic").rolling_mean(window_size=window)
            / pl.col("ic").rolling_std(window_size=window),
        )
        .select("trade_date", "rolling_ir")
    )


def quantile_nav_series(
    q_ret_df: pl.DataFrame,
    *,
    n_quantiles: int,
) -> pl.DataFrame:
    """Cumulative NAV (base 1.0) per quantile from per-date mean returns."""
    wide = q_ret_df.pivot(on="quantile", index="trade_date", values="mean_return")
    # 整数分位值经 pivot 后列名为其字符串形式；统一重命名为 q_{n}。
    wide = wide.rename(
        {column: f"q_{column}" for column in wide.columns if column != "trade_date"},
    )
    columns = [f"q_{q}" for q in range(1, n_quantiles + 1)]
    exprs: list[pl.Expr] = []
    for q in range(1, n_quantiles + 1):
        name = f"q_{q}"
        if name in wide.columns:
            exprs.append((1.0 + pl.col(name)).cum_prod().alias(name))
        else:
            exprs.append(pl.lit(None, dtype=pl.Float64).alias(name))
    return (
        wide.sort("trade_date")
        .with_columns(exprs)
        .with_columns(
            pl.col(column).fill_null(strategy="forward") for column in columns
        )
        .select(["trade_date", *columns])
    )


def ls_nav_series(
    q_ret_df: pl.DataFrame,
    *,
    top_quantile: int,
    bottom_quantile: int,
) -> pl.DataFrame:
    """Cumulative long-short NAV (base 1.0) from daily top-minus-bottom spread."""
    spread = (
        q_ret_df.filter(pl.col("quantile") == top_quantile)
        .select("trade_date", pl.col("mean_return").alias("top"))
        .join(
            q_ret_df.filter(pl.col("quantile") == bottom_quantile).select(
                "trade_date",
                pl.col("mean_return").alias("bottom"),
            ),
            on="trade_date",
            how="inner",
        )
        .sort("trade_date")
        .with_columns(spread=pl.col("top") - pl.col("bottom"))
    )
    return spread.select(
        "trade_date",
        ls_nav=(1.0 + pl.col("spread")).cum_prod(),
    )


def monthly_ic(ic_df: pl.DataFrame) -> pl.DataFrame:
    """Mean IC and observation count per (year, month)."""
    return (
        ic_df.with_columns(
            year=pl.col("trade_date").str.slice(0, 4).cast(pl.Int32),
            month=pl.col("trade_date").str.slice(5, 2).cast(pl.Int32),
        )
        .group_by("year", "month")
        .agg(mean_ic=pl.col("ic").mean(), days=pl.len())
        .sort("year", "month")
    )
