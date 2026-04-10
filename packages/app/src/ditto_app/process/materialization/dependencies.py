"""Dependency classification, resolution, and frame preparation helpers."""

from __future__ import annotations

from collections import defaultdict

import polars as pl

__all__ = [
    "apply_cs_amplification",
    "classify_dependencies",
    "join_frames",
    "prepare_derived_frame",
    "prepare_market_frame",
    "resolve_adj_type",
]


# ===========================================================================
# Cross-section amplification
# ===========================================================================


def apply_cs_amplification(
    *,
    frame: pl.DataFrame,
    instrument_ids: list[int],
    time_keys: tuple[str, ...] = ("trade_date",),
    entity_keys: tuple[str, ...] = ("instrument_id",),
) -> pl.DataFrame:
    """
    Expand a materialized frame to full cross-section coverage.

    Creates a cartesian product of all observed dates (from *time_keys*)
    with every instrument in *instrument_ids*, then left-joins the original
    frame so that missing (date, instrument) pairs appear as null rows.

    This is required for CS factors where the output is only meaningful
    when every instrument is present for each date.
    """
    if frame.is_empty() or not instrument_ids:
        return frame
    key_columns = list(entity_keys) + list(time_keys)
    extra_cols = ["availability_time"] if "availability_time" in frame.columns else []
    unique_dates = frame.select(pl.col(time_keys[0]).unique().sort()).to_series()
    cross = unique_dates.to_frame(time_keys[0]).join(
        pl.DataFrame({entity_keys[0]: instrument_ids}),
        how="cross",
    )
    return cross.join(
        frame.select([*key_columns, "value", *extra_cols]),
        on=key_columns,
        how="left",
    )


# ===========================================================================
# Dataset column registries
# ===========================================================================


_MARKET_DATASET_COLUMNS: dict[str, frozenset[str]] = {
    "market.stock_daily": frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
        }
    ),
    "market.adj_factor": frozenset({"adj_factor"}),
    "market.stock_status": frozenset(
        {"is_suspended", "suspend_timing", "is_st", "st_type", "list_status"}
    ),
}

_ETF_DATASET_COLUMNS: dict[str, frozenset[str]] = {
    "etf.daily": frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
            "pct_change",
        }
    ),
}


# ===========================================================================
# Dependency classification & resolution
# ===========================================================================


def classify_dependencies(
    dependencies: tuple[str, ...],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    list[str],
]:
    """Separate dependencies into market, ETF, and derived namespaces."""
    market_dependencies: dict[str, set[str]] = defaultdict(set)
    etf_dependencies: dict[str, set[str]] = defaultdict(set)
    derived_dependencies: list[str] = []

    for dependency in dependencies:
        if dependency.startswith("etf."):
            dataset_ref, column = _resolve_etf_dependency(dependency)
            etf_dependencies[dataset_ref].add(column)
        elif dependency.startswith("market."):
            dataset_ref, column = _resolve_market_dependency(dependency)
            market_dependencies[dataset_ref].add(column)
        elif "." in dependency:
            derived_dependencies.append(dependency)
        else:
            raise NotImplementedError(
                f"Unsupported dependency={dependency} (market.*, etf.*, @derived only)"
            )

    return (
        dict(market_dependencies),
        dict(etf_dependencies),
        derived_dependencies,
    )


def resolve_adj_type(spec: object) -> str:
    """Extract adj_type from spec's execution_policy, defaulting to 'none'."""
    ep = getattr(spec, "execution_policy", None)
    return ep.adj_type if ep else "none"


def _resolve_market_dependency(dependency: str) -> tuple[str, str]:
    """Resolve a 'market.*' dependency to (dataset_ref, column_name)."""
    column_name = dependency.removeprefix("market.")
    for dataset_ref, columns in _MARKET_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported market dependency={dependency}")


def _resolve_etf_dependency(dependency: str) -> tuple[str, str]:
    """Resolve an 'etf.*' dependency to (dataset_ref, column_name)."""
    column_name = dependency.removeprefix("etf.")
    for dataset_ref, columns in _ETF_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported ETF dependency={dependency}")


def prepare_market_frame(
    frame: pl.DataFrame,
    *,
    join_keys: list[str],
    value_columns: set[str],
    availability_column: str,
) -> pl.DataFrame:
    """Select join keys + value columns and alias availability time."""
    selected_columns = [*join_keys, *sorted(value_columns)]
    existing_columns = [
        column for column in selected_columns if column in frame.columns
    ]
    prepared = frame.select(existing_columns)
    return prepared.with_columns(
        pl.col(availability_column).alias("availability_time__0")
    )


def prepare_derived_frame(
    frame: pl.DataFrame,
    *,
    join_keys: list[str],
    column_name: str,
) -> pl.DataFrame:
    """Select join keys + value from an upstream derived frame and rename columns."""
    selected_columns = [*join_keys]
    if "value" in frame.columns:
        selected_columns.append("value")
    if "availability_time" in frame.columns:
        selected_columns.append("availability_time")
    prepared = frame.select(selected_columns)
    renamed: dict[str, str] = {}
    if "value" in prepared.columns:
        renamed["value"] = column_name
    if "availability_time" in prepared.columns:
        renamed["availability_time"] = "availability_time__0"
    return prepared.rename(renamed)


def join_frames(
    frames: list[pl.DataFrame],
    *,
    join_keys: list[str],
) -> pl.DataFrame:
    """Left-join multiple frames on *join_keys* and coalesce availability times."""
    base = frames[0]
    availability_columns = ["availability_time__0"]
    for index, frame in enumerate(frames[1:], start=1):
        renamed = {
            column: f"{column}__{index}"
            for column in frame.columns
            if column.startswith("availability_time__")
        }
        next_frame = frame.rename(renamed)
        availability_columns.extend(renamed.values())
        base = base.join(next_frame, on=join_keys, how="left")
    return base.with_columns(
        pl.max_horizontal(
            *(pl.col(column) for column in availability_columns),
        ).alias("availability_time"),
    ).drop(availability_columns)
