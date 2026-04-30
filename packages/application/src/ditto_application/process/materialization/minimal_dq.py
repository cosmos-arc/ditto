"""Minimal DQ summary — build quality records from materialized frames."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

import polars as pl
from ditto_analytics.publication_safety import DerivedMinimalDQSummary
from ditto_data.models.publication_safety import (
    DerivedMinimalDQSummaryRecord,
    JsonDict,
)
from ditto_kernel.strategy import DerivedSpec

from ditto_application.config import now_iso

__all__ = ["build_minimal_dq_record"]


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def build_minimal_dq_record(
    *,
    spec: DerivedSpec,
    run_id: str,
    version: int,
    frame: pl.DataFrame,
) -> DerivedMinimalDQSummaryRecord:
    """Build a minimal DQ summary record for a materialization run."""
    summary = _build_minimal_dq_summary(spec=spec, frame=frame)
    return DerivedMinimalDQSummaryRecord(
        derived_id=spec.id,
        version=version,
        run_id=run_id,
        passed=summary.is_passed(),
        error_count=summary.error_count(),
        payload=cast(JsonDict, asdict(summary)),
        created_at=now_iso(),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_minimal_dq_summary(
    *,
    spec: DerivedSpec,
    frame: pl.DataFrame,
) -> DerivedMinimalDQSummary:
    primary_key_columns = tuple(
        dict.fromkeys((*spec.entity_keys, *spec.effective_time_keys))
    )
    missing_primary_key_columns = tuple(
        column for column in primary_key_columns if column not in frame.columns
    )
    row_count = frame.height
    failed_checks: list[str] = []
    if row_count <= 0:
        failed_checks.append("row_count_positive")

    null_primary_key_count = 0
    duplicate_key_count = 0
    if missing_primary_key_columns:
        failed_checks.append("primary_keys_present")
    elif row_count > 0:
        null_primary_key_count = _count_null_primary_keys(
            frame=frame,
            primary_key_columns=primary_key_columns,
        )
        duplicate_key_count = _count_duplicate_primary_keys(
            frame=frame,
            primary_key_columns=primary_key_columns,
        )
        if null_primary_key_count > 0:
            failed_checks.append("primary_keys_present")
        if duplicate_key_count > 0:
            failed_checks.append("primary_keys_unique")

    null_value_count = 0
    nan_value_count = 0
    computable_value_count = 0
    coverage_rate = 0.0
    value_mean = 0.0
    value_std = 0.0
    value_skewness = 0.0
    value_jump_rate = 0.0
    max_consecutive_nulls = 0
    if "value" not in frame.columns:
        failed_checks.append("value_column_present")
    else:
        null_value_count = int(frame.select(pl.col("value").is_null().sum()).item())
        nan_value_count = _count_nan_values(frame)
        computable_value_count = _count_computable_values(
            frame=frame,
            null_value_count=null_value_count,
            nan_value_count=nan_value_count,
        )
        if computable_value_count <= 0:
            failed_checks.append("value_has_computable_rows")
        if nan_value_count > 0:
            failed_checks.append("value_has_no_nan")

        # Enhanced DQ statistics (PUB-PB-1)
        coverage_rate = computable_value_count / row_count if row_count > 0 else 0.0
        value_stats = _compute_value_statistics(frame)
        value_mean = value_stats["mean"]
        value_std = value_stats["std"]
        value_skewness = value_stats["skewness"]
        value_jump_rate = _compute_value_jump_rate(frame)
        max_consecutive_nulls = _compute_max_consecutive_nulls(
            frame,
            spec.effective_time_keys,
        )

    return DerivedMinimalDQSummary(
        row_count=row_count,
        primary_key_columns=primary_key_columns,
        missing_primary_key_columns=missing_primary_key_columns,
        null_primary_key_count=null_primary_key_count,
        duplicate_key_count=duplicate_key_count,
        null_value_count=null_value_count,
        nan_value_count=nan_value_count,
        computable_value_count=computable_value_count,
        failed_checks=tuple(failed_checks),
        coverage_rate=coverage_rate,
        value_mean=value_mean,
        value_std=value_std,
        value_skewness=value_skewness,
        distribution_drift=None,
        value_jump_rate=value_jump_rate,
        max_consecutive_nulls=max_consecutive_nulls,
    )


def _count_null_primary_keys(
    *,
    frame: pl.DataFrame,
    primary_key_columns: tuple[str, ...],
) -> int:
    if not primary_key_columns or frame.is_empty():
        return 0
    return int(
        frame.select(
            pl.any_horizontal(
                [pl.col(column).is_null() for column in primary_key_columns]
            ).sum()
        ).item()
    )


def _count_duplicate_primary_keys(
    *,
    frame: pl.DataFrame,
    primary_key_columns: tuple[str, ...],
) -> int:
    if not primary_key_columns or frame.is_empty():
        return 0
    duplicate_rows = (
        frame.group_by(list(primary_key_columns)).len().filter(pl.col("len") > 1)
    )
    if duplicate_rows.is_empty():
        return 0
    return int(duplicate_rows.select((pl.col("len") - 1).sum()).item())


def _count_nan_values(frame: pl.DataFrame) -> int:
    if "value" not in frame.columns:
        return 0
    value_dtype = frame.schema["value"]
    if value_dtype not in (pl.Float32(), pl.Float64()):
        return 0
    return int(frame.select(pl.col("value").is_nan().sum()).item())


def _count_computable_values(
    *,
    frame: pl.DataFrame,
    null_value_count: int,
    nan_value_count: int,
) -> int:
    if "value" not in frame.columns:
        return 0
    return frame.height - null_value_count - nan_value_count


def _compute_value_statistics(frame: pl.DataFrame) -> dict[str, float]:
    """Compute mean, std, and skewness of non-null, non-NaN values."""
    clean = frame.select(
        pl.col("value").drop_nulls().drop_nans().alias("v"),
    )
    if clean.is_empty():
        return {"mean": 0.0, "std": 0.0, "skewness": 0.0}

    mean_val = float(clean.select(pl.col("v").mean()).item() or 0.0)
    std_val = float(clean.select(pl.col("v").std(ddof=1)).item() or 0.0)
    # Skewness = E[((x - mean) / std)^3]
    if std_val > 0:
        skewness = float(
            clean.select(
                ((pl.col("v") - mean_val) / std_val).pow(3).mean(),
            ).item()
            or 0.0,
        )
    else:
        skewness = 0.0
    return {"mean": mean_val, "std": std_val, "skewness": skewness}


def _compute_value_jump_rate(frame: pl.DataFrame) -> float:
    """
    Compute the fraction of jumps exceeding 3sigma in consecutive value pct_changes.

    For each entity, compute pct_change between consecutive time-ordered rows.
    A "jump" is ``abs(pct_change) > 3 * pct_change_std`` (z-score logic).

    The threshold is derived from the pct_change distribution itself, ensuring
    correct scale matching.
    """
    time_keys = [col for col in frame.columns if col in ("trade_date", "date", "time")]
    entity_keys = [
        col for col in frame.columns if col in ("instrument_id", "entity_id", "code")
    ]

    if not time_keys or not entity_keys:
        return 0.0

    computable = frame.filter(
        pl.col("value").is_not_null() & pl.col("value").is_not_nan(),
    ).sort(entity_keys + time_keys)

    _MIN_PCT_CHANGE_OBS = 2
    if computable.height < _MIN_PCT_CHANGE_OBS:
        return 0.0

    pct_changes = computable.group_by(entity_keys[0], maintain_order=True).agg(
        pct=pl.col("value").pct_change(1).drop_nulls(),
    )

    if pct_changes.is_empty():
        return 0.0

    all_pct = pct_changes.select(pl.col("pct").explode())
    if all_pct.is_empty():
        return 0.0

    all_pct_values = all_pct.to_series()
    pct_std_raw = all_pct_values.std()
    if pct_std_raw is None or not isinstance(pct_std_raw, float) or pct_std_raw <= 0:
        return 0.0

    threshold = 3.0 * pct_std_raw
    n_total = all_pct.height
    n_jumps = int(all_pct.filter(pl.col("pct").abs() > threshold).height)
    return n_jumps / n_total if n_total > 0 else 0.0


def _compute_max_consecutive_nulls(
    frame: pl.DataFrame,
    time_keys: tuple[str, ...] | None,
) -> int:
    """
    Compute the longest streak of consecutive null values.

    Scans the frame sorted by entity then time, counting the maximum run of
    consecutive null "value" entries within each entity.
    """
    entity_keys = [
        col for col in frame.columns if col in ("instrument_id", "entity_id", "code")
    ]
    effective_time_keys = list(time_keys or [])
    # Fall back to any known time column
    if not effective_time_keys:
        for col in ("trade_date", "date", "time"):
            if col in frame.columns:
                effective_time_keys = [col]
                break

    if not entity_keys or not effective_time_keys:
        # No entity/time keys: count consecutive nulls in order
        if "value" not in frame.columns or frame.is_empty():
            return 0
        is_null_series = frame.select(pl.col("value").is_null()).to_series()
        return _max_consecutive_true(is_null_series)

    sort_keys = entity_keys + effective_time_keys
    sorted_frame = frame.sort(sort_keys)

    # Per entity, compute max consecutive nulls
    max_streak = 0
    for entity_df in sorted_frame.group_by(entity_keys[0]):
        group = entity_df[1]
        if "value" not in group.columns:
            continue
        is_null_series = group.select(pl.col("value").is_null()).to_series()
        streak = _max_consecutive_true(is_null_series)
        max_streak = max(max_streak, streak)

    return max_streak


def _max_consecutive_true(series: pl.Series) -> int:
    """Return the longest consecutive run of True values in a boolean series."""
    if series.is_empty():
        return 0
    current = 0
    max_run = 0
    for val in series.to_list():
        if val is True or val == 1:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run
