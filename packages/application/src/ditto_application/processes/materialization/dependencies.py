"""Dependency classification, resolution, and frame preparation helpers."""

from __future__ import annotations

import polars as pl
from ditto_features.materialization.dependency_registry import (
    DependencyContract,
    missing_contract_columns,
)
from ditto_features.materialization.dependency_registry import (
    classify_dependencies as _classify_dependencies,
)

from ditto_application.processes.materialization.types import MissingDependencyError

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
    groups = _classify_dependencies(dependencies)
    return (
        {key: set(value) for key, value in groups.market.items()},
        {key: set(value) for key, value in groups.etf.items()},
        list(groups.derived),
    )


def resolve_adj_type(spec: object) -> str:
    """Extract adj_type from spec's execution_policy, defaulting to 'none'."""
    ep = getattr(spec, "execution_policy", None)
    return ep.adj_type if ep else "none"


def prepare_market_frame(
    frame: pl.DataFrame,
    *,
    join_keys: list[str],
    value_columns: set[str],
    availability_column: str,
    contract: DependencyContract | None = None,
) -> pl.DataFrame:
    """Select join keys + value columns and alias availability time."""
    missing = _missing_market_frame_columns(
        frame=frame,
        join_keys=join_keys,
        value_columns=value_columns,
        availability_column=availability_column,
        contract=contract,
    )
    if missing:
        raise MissingDependencyError(
            missing=list(missing), available=list(frame.columns)
        )

    selected_columns = _dedupe_columns(
        (*join_keys, availability_column, *sorted(value_columns))
    )
    prepared = frame.select(selected_columns)
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


def _missing_market_frame_columns(
    *,
    frame: pl.DataFrame,
    join_keys: list[str],
    value_columns: set[str],
    availability_column: str,
    contract: DependencyContract | None,
) -> tuple[str, ...]:
    """Return source-frame columns required by runtime dependency loading."""
    missing = list(
        missing_contract_columns(contract, tuple(frame.columns)) if contract else ()
    )
    fallback_required = _dedupe_columns(
        (*join_keys, availability_column, *sorted(value_columns))
    )
    for column in fallback_required:
        if column not in frame.columns and column not in missing:
            missing.append(column)
    return tuple(missing)


def _dedupe_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    """Dedupe columns while preserving the caller's semantic order."""
    deduped: list[str] = []
    seen: set[str] = set()
    for column in columns:
        if column in seen:
            continue
        deduped.append(column)
        seen.add(column)
    return tuple(deduped)
