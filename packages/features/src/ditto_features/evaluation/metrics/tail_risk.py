"""Tail risk metrics and Grinold-Kahn IR."""

from __future__ import annotations

import math

import polars as pl

from ditto_features.evaluation.report import TailRiskMetrics

from ._math import MIN_TAIL_OBSERVATIONS, scalar_to_float

__all__ = [
    "grinold_kahn_ir",
    "tail_risk_metrics",
]


# ---------------------------------------------------------------------------
# Tail risk metrics
# ---------------------------------------------------------------------------


def tail_risk_metrics(ls_daily: pl.Series) -> TailRiskMetrics:
    """
    Compute tail risk statistics from a daily long-short returns series.

    Args:
        ls_daily: Daily long-short returns as a Polars Series.

    Returns:
        A :class:`~ditto_features.evaluation.report.TailRiskMetrics` instance.
        Returns all zeros if the series is empty or has fewer than 2 elements.

    """
    n = len(ls_daily)
    if n < MIN_TAIL_OBSERVATIONS:
        return TailRiskMetrics(
            cvar_95=0.0,
            cvar_99=0.0,
            skewness=0.0,
            kurtosis=0.0,
            max_single_day_loss=scalar_to_float(ls_daily.min()) if n == 1 else 0.0,
        )

    sorted_vals = ls_daily.sort()

    # CVaR 95%: mean of worst 5%.
    cutoff_95 = max(1, math.ceil(n * 0.05))
    worst_95 = sorted_vals.slice(0, cutoff_95)
    cvar_95 = scalar_to_float(worst_95.mean())

    # CVaR 99%: mean of worst 1%.
    cutoff_99 = max(1, math.ceil(n * 0.01))
    worst_99 = sorted_vals.slice(0, cutoff_99)
    cvar_99 = scalar_to_float(worst_99.mean())

    # Skewness and excess kurtosis.
    skewness = scalar_to_float(ls_daily.skew())
    kurtosis = scalar_to_float(ls_daily.kurtosis()) - 3.0

    # Max single day loss.
    max_single_day_loss = scalar_to_float(ls_daily.min())

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
