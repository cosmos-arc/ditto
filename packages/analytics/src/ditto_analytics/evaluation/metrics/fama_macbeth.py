"""Fama-MacBeth two-pass regression."""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from ditto_analytics.evaluation.report import FamaMacBethResult

from ._math import EvaluationColumns, two_sided_p_value

__all__ = ["fama_macbeth"]


def fama_macbeth(
    factor_df: pl.DataFrame,
    return_df: pl.DataFrame,
    *,
    risk_factors: dict[str, pl.DataFrame] | None = None,
    min_cross_section: int = 30,
    columns: EvaluationColumns = EvaluationColumns(),
) -> FamaMacBethResult:
    """
    Fama-MacBeth two-pass regression.

    **First pass (cross-section):** For each date, run an OLS regression of
    returns on the target factor (and optionally risk factors).  Record the
    slope coefficient for the target factor and the R².

    **Second pass (time-series):** Compute mean, standard error, t-statistic,
    and p-value of the target factor's slope across all dates.

    Args:
        factor_df: Target factor values ``pl.DataFrame[date, entity, value]``.
        return_df: Forward returns ``pl.DataFrame[date, entity, forward_return]``.
        risk_factors: Optional ``{name: DataFrame[date, entity, value]}`` of
            additional control factors.
        min_cross_section: Minimum number of entities per date for a valid
            cross-section regression.
        columns: Column name configuration via :class:`EvaluationColumns`.

    Returns:
        A :class:`~ditto_analytics.evaluation.report.FamaMacBethResult`.

    """
    # Zero result for degenerate cases.
    _empty = FamaMacBethResult(
        factor_exposure=0.0,
        exposure_t_stat=0.0,
        exposure_p_value=1.0,
        exposure_stderr=0.0,
        r_squared_avg=0.0,
        n_periods=0,
        slopes=(),
    )

    date_col = columns.date
    entity_col = columns.entity
    factor_col = columns.factor
    return_col = columns.return_col

    # Join factor and return data.
    joined = factor_df.join(return_df, on=[date_col, entity_col], how="inner")
    if joined.height == 0:
        return _empty

    # Join risk factors if provided.
    risk_names: list[str] = []
    if risk_factors:
        for rf_name, rf_df in risk_factors.items():
            joined = joined.join(
                rf_df.rename({factor_col: f"risk_{rf_name}"}),
                on=[date_col, entity_col],
                how="inner",
            )
            risk_names.append(rf_name)

    target_slopes, r_squareds, risk_slopes_per_date = _run_cross_section_regressions(
        joined,
        date_col=date_col,
        entity_col=entity_col,
        factor_col=factor_col,
        return_col=return_col,
        risk_names=risk_names,
        min_cross_section=min_cross_section,
    )

    if not target_slopes:
        return _empty

    return _aggregate_fm_results(
        target_slopes,
        r_squareds,
        risk_names,
        risk_slopes_per_date,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _run_cross_section_regressions(
    joined: pl.DataFrame,
    *,
    date_col: str,
    entity_col: str,
    factor_col: str,
    return_col: str,
    risk_names: list[str],
    min_cross_section: int,
) -> tuple[list[float], list[float], list[list[float]]]:
    """
    Run per-date cross-section OLS regressions.

    Returns ``(target_slopes, r_squareds, risk_slopes_per_date)``.
    """
    dates = joined.select(pl.col(date_col)).unique().sort(date_col)
    target_slopes: list[float] = []
    r_squareds: list[float] = []
    risk_slopes_per_date: list[list[float]] = [[] for _ in risk_names]

    for date_row in dates.iter_rows(named=True):
        dt = date_row[date_col]
        cross = joined.filter(pl.col(date_col) == dt)
        n = cross.height
        if n < min_cross_section:
            continue

        # Build design matrix: [1, f_target, f_risk1, f_risk2, ...]
        f_target = cross[factor_col].to_numpy()
        y = cross[return_col].to_numpy()

        # Demean for numerical stability.
        y_c = y - y.mean()

        x_cols: list[list[float]] = []
        # Target factor (demeaned).
        f_mean = f_target.mean()
        x_cols.append((f_target - f_mean).tolist())
        # Risk factors (demeaned).
        for rf_name in risk_names:
            rf_vals = cross[f"risk_{rf_name}"].to_numpy()
            rf_mean = rf_vals.mean()
            x_cols.append((rf_vals - rf_mean).tolist())

        # Single factor (no risk factors): simple OLS.
        if not risk_names:
            x_c_arr = f_target - f_mean

            var_f = float(x_c_arr @ x_c_arr)
            if var_f == 0:
                continue
            cov_f_r = float(x_c_arr @ y_c)
            beta = cov_f_r / var_f

            # R² = corr²
            std_f = math.sqrt(var_f / n) if n > 1 else 0.0
            std_y = math.sqrt(float(y_c @ y_c) / n) if n > 1 else 0.0
            r_sq = 0.0
            if std_f > 0 and std_y > 0:
                corr_val = cov_f_r / (n * std_f * std_y)
                r_sq = corr_val * corr_val

            target_slopes.append(beta)
            r_squareds.append(r_sq)
        else:
            # Multi-factor OLS via matrix approach.
            # Build full design matrix (demeaned, so intercept is implicit).
            X: np.ndarray = np.column_stack(x_cols).astype(np.float64)

            # X'X and X'y
            XtX: np.ndarray = X.T @ X  # (k, k)
            Xty: np.ndarray = X.T @ y_c  # (k,)

            try:
                beta_vec: np.ndarray = np.linalg.solve(XtX, Xty)  # (k,)
            except np.linalg.LinAlgError:
                continue

            # Target factor slope is beta_vec[0].
            target_slopes.append(float(beta_vec[0]))
            for i, _rf_name in enumerate(risk_names):
                risk_slopes_per_date[i].append(float(beta_vec[i + 1]))

            # R² = 1 - SSE/SST
            y_pred: np.ndarray = X @ beta_vec
            sse = float(np.sum((y_c - y_pred) ** 2))
            sst = float(np.sum(y_c**2))
            r_sq = 1.0 - sse / sst if sst > 0 else 0.0
            r_squareds.append(r_sq)

    return target_slopes, r_squareds, risk_slopes_per_date


def _aggregate_fm_results(
    target_slopes: list[float],
    r_squareds: list[float],
    risk_names: list[str],
    risk_slopes_per_date: list[list[float]],
) -> FamaMacBethResult:
    """Compute time-series statistics from cross-section regression results."""
    n_periods = len(target_slopes)
    mean_slope = sum(target_slopes) / n_periods

    if n_periods == 1:
        return FamaMacBethResult(
            factor_exposure=mean_slope,
            exposure_t_stat=0.0,
            exposure_p_value=1.0,
            exposure_stderr=0.0,
            r_squared_avg=sum(r_squareds) / n_periods if r_squareds else 0.0,
            n_periods=n_periods,
            slopes=_build_slopes_tuple(
                mean_slope,
                target_slopes,
                risk_names,
                risk_slopes_per_date,
            ),
        )

    # Time-series statistics.
    var_slopes = sum((s - mean_slope) ** 2 for s in target_slopes) / (n_periods - 1)
    std_slopes = math.sqrt(var_slopes) if var_slopes > 0 else 0.0
    stderr = std_slopes / math.sqrt(n_periods)
    t_stat = mean_slope / stderr if stderr > 0 else 0.0
    p_value = two_sided_p_value(t_stat, n_periods - 1)
    r_sq_avg = sum(r_squareds) / len(r_squareds) if r_squareds else 0.0

    return FamaMacBethResult(
        factor_exposure=mean_slope,
        exposure_t_stat=t_stat,
        exposure_p_value=p_value,
        exposure_stderr=stderr,
        r_squared_avg=r_sq_avg,
        n_periods=n_periods,
        slopes=_build_slopes_tuple(
            mean_slope,
            target_slopes,
            risk_names,
            risk_slopes_per_date,
        ),
    )


def _build_slopes_tuple(
    target_mean: float,
    _target_slopes: list[float],
    risk_names: list[str],
    risk_slopes_per_date: list[list[float]],
) -> tuple[tuple[str, float], ...]:
    """Build the slopes tuple for FamaMacBethResult."""
    items: list[tuple[str, float]] = [("target", target_mean)]
    for i, rf_name in enumerate(risk_names):
        slopes = risk_slopes_per_date[i]
        if slopes:
            items.append((rf_name, sum(slopes) / len(slopes)))
        else:
            items.append((rf_name, 0.0))
    return tuple(items)
