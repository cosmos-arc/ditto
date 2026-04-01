"""Factor analysis: orthogonalization, Fama-MacBeth, exposure, attribution."""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from ditto_engine.engine.evaluation.report import (
    FactorExposureResult,
    FamaMacBethResult,
    PerformanceAttributionResult,
)

from ._math import (
    IR_TE_EPSILON,
    MIN_CORR_PAIRS,
    EvaluationColumns,
    scalar_to_float,
    two_sided_p_value,
)
from .ic import ic_summary, rank_ic

__all__ = [
    "factor_exposure",
    "fama_macbeth",
    "orthogonalize",
    "performance_attribution",
]


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
        A :class:`~ditto_engine.engine.evaluation.report.FamaMacBethResult`.

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


# ---------------------------------------------------------------------------
# Factor exposure analysis
# ---------------------------------------------------------------------------


def factor_exposure(
    target_df: pl.DataFrame,
    risk_factor_dfs: dict[str, pl.DataFrame],
    *,
    return_df: pl.DataFrame | None = None,
    min_cross_section: int = 30,
    method: str = "sequential",
    columns: EvaluationColumns = EvaluationColumns(),
) -> FactorExposureResult:
    """
    Factor exposure analysis.

    Quantify how much the target factor is explained by risk factors.

    Steps:
    1. Compute pairwise correlation matrix of target + all risk factors
       (per-date, then average).
    2. For each risk factor, orthogonalise the target against it and compute
       the residual IC with returns.
    3. Target exposure: R² contribution of each risk factor.

    Args:
        target_df: ``pl.DataFrame[date, entity, value]`` — target factor.
        risk_factor_dfs: ``{name: DataFrame[date, entity, value]}`` — risk
            factors.
        return_df: Optional ``pl.DataFrame[date, entity, forward_return]``
            for computing residual IC.  If ``None``, orthogonal residual stats
            will be empty.
        min_cross_section: Minimum observations per date.
        method: Orthogonalization method (``"sequential"`` or ``"symmetric"``).
        columns: Column name configuration via :class:`EvaluationColumns`.

    Returns:
        A :class:`~ditto_engine.engine.evaluation.report.FactorExposureResult`.

    """
    # Build the empty result early for early-return paths.
    _empty_result = FactorExposureResult(
        target_exposure={},
        correlation_matrix={},
        orthogonal_residual_stats={},
        n_factors=0,
        n_dates=0,
    )

    if not risk_factor_dfs or target_df.height == 0:
        return _empty_result

    date_col = columns.date
    entity_col = columns.entity
    value_col = columns.factor

    # Collect all factor names: "target" + risk factor names.
    all_names = ["target", *risk_factor_dfs]

    # Build a long-format DataFrame with all factors for correlation.
    long_frames: list[pl.DataFrame] = []
    long_frames.append(
        target_df.select(
            pl.col(date_col),
            pl.col(entity_col),
            pl.col(value_col),
            pl.lit("target").alias("factor_name"),
        ),
    )
    for rf_name, rf_df in risk_factor_dfs.items():
        long_frames.append(
            rf_df.select(
                pl.col(date_col),
                pl.col(entity_col),
                pl.col(value_col),
                pl.lit(rf_name).alias("factor_name"),
            ),
        )
    all_factors = pl.concat(long_frames, how="diagonal")

    # Count dates and filter by min_cross_section.
    dates = target_df.select(pl.col(date_col)).unique().sort(date_col)
    valid_dates: list[object] = []
    for date_row in dates.iter_rows(named=True):
        dt = date_row[date_col]
        cross = all_factors.filter(pl.col(date_col) == dt)
        # Check that all factors have enough observations.
        if cross.height < min_cross_section * len(all_names):
            continue
        # Check each factor individually has enough.
        per_factor_ok = True
        for fname in all_names:
            factor_rows = cross.filter(pl.col("factor_name") == fname)
            if factor_rows.height < min_cross_section:
                per_factor_ok = False
                break
        if per_factor_ok:
            valid_dates.append(dt)

    if not valid_dates:
        return _empty_result

    n_dates = len(valid_dates)
    n_factors = len(risk_factor_dfs)

    # 1. Compute pairwise correlation matrix (average across dates).
    corr_matrix = _compute_pairwise_correlations(
        all_factors,
        all_names,
        valid_dates,
        date_col=date_col,
        entity_col=entity_col,
        value_col=value_col,
        n_dates=n_dates,
    )

    # 2. For each risk factor, orthogonalise target and compute residual IC.
    cols = EvaluationColumns(date=date_col, entity=entity_col, factor=value_col)
    target_exposure, orthogonal_residual_stats = _compute_factor_exposures(
        target_df,
        risk_factor_dfs,
        return_df,
        columns=cols,
        method=method,
        min_cross_section=min_cross_section,
    )

    return FactorExposureResult(
        target_exposure=target_exposure,
        correlation_matrix=corr_matrix,
        orthogonal_residual_stats=orthogonal_residual_stats,
        n_factors=n_factors,
        n_dates=n_dates,
    )


def _compute_pairwise_correlations(
    all_factors: pl.DataFrame,
    all_names: list[str],
    valid_dates: list[object],
    *,
    date_col: str,
    entity_col: str,
    value_col: str,
    n_dates: int,
) -> dict[str, dict[str, float]]:
    """Compute pairwise correlation matrix averaged across dates."""
    corr_matrix: dict[str, dict[str, float]] = {name: {} for name in all_names}
    for name_a in all_names:
        for name_b in all_names:
            corr_matrix[name_a][name_b] = 0.0

    for dt in valid_dates:
        cross = all_factors.filter(pl.col(date_col) == dt)
        # Build wide format manually: group by entity, collect factor values.
        entity_list = cross.select(pl.col(entity_col)).unique().to_series().to_list()

        # Extract arrays for each factor.
        factor_arrays: dict[str, np.ndarray] = {}
        for fname in all_names:
            factor_rows = cross.filter(pl.col("factor_name") == fname)
            # Build entity -> value map.
            val_map = dict(
                zip(
                    factor_rows[entity_col].to_list(),
                    factor_rows[value_col].to_list(),
                    strict=False,
                ),
            )
            arr = np.array([val_map.get(e, float("nan")) for e in entity_list])
            factor_arrays[fname] = arr

        for name_a in all_names:
            a_vals = factor_arrays[name_a]
            for name_b in all_names:
                b_vals = factor_arrays[name_b]
                # Compute correlation on valid (non-NaN) pairs.
                valid_mask = ~(np.isnan(a_vals) | np.isnan(b_vals))
                n_valid = int(valid_mask.sum())
                if n_valid < MIN_CORR_PAIRS:
                    continue
                a_sub = a_vals[valid_mask]
                b_sub = b_vals[valid_mask]
                a_mean = a_sub.mean()
                b_mean = b_sub.mean()
                da = a_sub - a_mean
                db = b_sub - b_mean
                num = float(da @ db)
                den = math.sqrt(float(da @ da) * float(db @ db))
                if den > 0:
                    corr_matrix[name_a][name_b] += num / den / n_dates

    # Ensure self-correlation is exactly 1.0.
    for name in all_names:
        corr_matrix[name][name] = 1.0

    return corr_matrix


def _compute_factor_exposures(
    target_df: pl.DataFrame,
    risk_factor_dfs: dict[str, pl.DataFrame],
    return_df: pl.DataFrame | None,
    *,
    columns: EvaluationColumns,
    method: str,
    min_cross_section: int,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Orthogonalise target against each risk factor and compute exposure metrics.

    Returns ``(target_exposure, orthogonal_residual_stats)``.
    """
    date_col = columns.date
    entity_col = columns.entity
    value_col = columns.factor
    target_exposure: dict[str, float] = {}
    orthogonal_residual_stats: dict[str, float] = {}

    for rf_name, rf_df in risk_factor_dfs.items():
        rf_long = rf_df.select(
            pl.col(date_col),
            pl.col(entity_col),
            pl.col(value_col),
            pl.lit(rf_name).alias("factor_name"),
        )
        residual_df = orthogonalize(
            target_df,
            rf_long,
            date_col=date_col,
            entity_col=entity_col,
            value_col=value_col,
            method=method,
            min_cross_section=min_cross_section,
        )

        if residual_df.height == 0:
            target_exposure[rf_name] = 0.0
            orthogonal_residual_stats[rf_name] = 0.0
            continue

        # R² exposure: 1 - (var_residual / var_target).
        residual_vals = residual_df["orthogonalized_value"].drop_nulls()
        target_vals = target_df[value_col].drop_nulls()
        var_residual = scalar_to_float(residual_vals.var())
        var_target = scalar_to_float(target_vals.var())

        if var_target > 0:
            target_exposure[rf_name] = max(0.0, 1.0 - var_residual / var_target)
        else:
            target_exposure[rf_name] = 0.0

        # Compute residual IC if return data is provided.
        if return_df is not None and return_df.height > 0:
            residual_for_ic = residual_df.rename(
                {"orthogonalized_value": value_col},
            )
            ic_df = rank_ic(
                residual_for_ic,
                return_df,
                factor_col=value_col,
                return_col="forward_return",
                date_col=date_col,
                entity_col=entity_col,
            )
            orthogonal_residual_stats[rf_name] = ic_summary(ic_df).mean
        else:
            orthogonal_residual_stats[rf_name] = 0.0

    return target_exposure, orthogonal_residual_stats


# ---------------------------------------------------------------------------
# Performance attribution (EVAL-EV-9)
# ---------------------------------------------------------------------------


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
        A :class:`~ditto_engine.engine.evaluation.report.PerformanceAttributionResult`.

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


# ---------------------------------------------------------------------------
# Orthogonalization helpers (private)
# ---------------------------------------------------------------------------


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
