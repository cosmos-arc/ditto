"""Factor orthogonalization via regression residuals."""

from __future__ import annotations

import math

import polars as pl

from ditto_features.errors import EvaluationError

__all__ = ["orthogonalize"]

_SUPPORTED_METHODS = ("sequential", "symmetric")


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

    * **sequential** -- OLS residual of *target* on each factor one at a time
      (successive orthogonalisation).
    * **symmetric** -- project out the first principal component of the factor
      matrix.

    Args:
        target: ``pl.DataFrame[date, entity, value]`` -- factor to orthogonalise.
        factors: ``pl.DataFrame[date, entity, value]`` -- control factors.
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

    raise EvaluationError(
        f"Unknown orthogonalization method: {method!r}",
        field="method",
        value=method,
        supported=_SUPPORTED_METHODS,
    )


# ---------------------------------------------------------------------------
# Private helpers
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
