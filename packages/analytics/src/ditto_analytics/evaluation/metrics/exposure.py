"""Factor exposure analysis."""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from ditto_analytics.evaluation.report import FactorExposureResult

from ._math import MIN_CORR_PAIRS, EvaluationColumns, scalar_to_float
from .ic import ic_summary, rank_ic
from .orthogonalization import orthogonalize

__all__ = ["factor_exposure"]


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
        target_df: ``pl.DataFrame[date, entity, value]`` -- target factor.
        risk_factor_dfs: ``{name: DataFrame[date, entity, value]}`` -- risk
            factors.
        return_df: Optional ``pl.DataFrame[date, entity, forward_return]``
            for computing residual IC.  If ``None``, orthogonal residual stats
            will be empty.
        min_cross_section: Minimum observations per date.
        method: Orthogonalization method (``"sequential"`` or ``"symmetric"``).
        columns: Column name configuration via :class:`EvaluationColumns`.

    Returns:
        A :class:`~ditto_analytics.evaluation.report.FactorExposureResult`.

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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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
