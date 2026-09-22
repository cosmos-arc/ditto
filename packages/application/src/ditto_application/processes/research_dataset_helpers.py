"""
Pure helper functions for research dataset snapshot construction.

Used by the explicit research dataset build process.
All symbols are private by convention (``_`` prefix); the owning consumers are
``ResearchDatasetBuildProcess`` and its unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

import polars as pl
from ditto_analysis.research.records import (
    ResearchDatasetSpecRecord,
    ResearchSpineSpecRecord,
)
from ditto_analysis.research.specs import (
    KnownAtPolicy,
    LateArrivalPolicy,
    ResearchDatasetSpec,
    SpineSpec,
)
from ditto_features.errors import DerivedValidationError
from ditto_kernel.market import CalendarId, GrainId

from ditto_application.exceptions import AppQueryError

__all__ = [
    "_DatasetSnapshotContract",
    "_attach_known_at",
    "_build_dataset_report",
    "_collect_null_counts",
    "_hydrate_dataset_spec",
    "_hydrate_spine_spec",
    "_normalize_trade_dates",
    "_parse_cutoff",
    "_pit_join",
    "_source_value_column",
]

# ---------------------------------------------------------------------------
# Shared frozen contract (used by facade methods *and* report builder)
# ---------------------------------------------------------------------------

_RESEARCH_BUILDER_VERSION = "historical-universe-research-v3"

_MARKET_TZ = ZoneInfo("Asia/Shanghai")
_MARKET_TZ_NAME = "Asia/Shanghai"

# "YYYY-MM-DD" is 10 bytes; anything longer declares intraday precision.
_DATE_ONLY_TEXT_WIDTH = 10


@dataclass(frozen=True)
class _DatasetSnapshotContract:
    """Frozen contract payload persisted with each dataset snapshot."""

    known_at_policy: KnownAtPolicy
    effective_cutoff: str | None
    resolved_versions: dict[str, int]
    resolved_inputs: tuple[dict[str, str | int | list[str]], ...]
    source_snapshot_ids: tuple[str, ...]
    builder_version: str = _RESEARCH_BUILDER_VERSION


# ---------------------------------------------------------------------------
# Hydration helpers
# ---------------------------------------------------------------------------


def _hydrate_spine_spec(record: ResearchSpineSpecRecord) -> SpineSpec:
    return SpineSpec(
        spine_id=record.spine_id,
        universe_id=record.universe_id,
        version=record.version,
        calendar=cast(CalendarId, record.calendar),
        grain=cast(GrainId, record.grain),
        entity_key=record.entity_key,
        description=record.description,
    )


def _hydrate_dataset_spec(record: ResearchDatasetSpecRecord) -> ResearchDatasetSpec:
    return ResearchDatasetSpec(
        dataset_id=record.dataset_id,
        spine_id=record.spine_id,
        derived_ids=record.derived_ids,
        version=record.version,
        join_policy=record.join_policy,
        known_at_policy=KnownAtPolicy(record.known_at_policy),
        late_arrival_policy=LateArrivalPolicy(record.late_arrival_policy),
        description=record.description,
    )


# ---------------------------------------------------------------------------
# Frame transformation helpers
# ---------------------------------------------------------------------------


def _normalize_trade_dates(calendar_frame: pl.DataFrame) -> pl.DataFrame:
    if calendar_frame.is_empty():
        return pl.DataFrame(schema={"trade_date": pl.Date})
    return calendar_frame.select(_date_column(pl.col("trade_date")))


def _date_column(column: pl.Expr) -> pl.Expr:
    """Normalize Date or ISO-string trade dates to plain calendar dates."""
    return column.cast(pl.Utf8).str.slice(0, 10).str.to_date()


def _sample_instant(column: pl.Expr) -> pl.Expr:
    """sample_time observes at Shanghai midnight of each trade date."""
    return (
        _date_column(column)
        .cast(pl.Datetime("us"))
        .dt.replace_time_zone(_MARKET_TZ_NAME)
    )


def _end_of_day_instant(column: pl.Expr) -> pl.Expr:
    """Date-only evidence is provably known no earlier than the end of its day."""
    return (
        _date_column(column)
        .cast(pl.Datetime("us"))
        .dt.replace_time_zone(_MARKET_TZ_NAME)
        .dt.offset_by("1d")
        .dt.offset_by("-1us")
    )


def _parse_cutoff(explicit_cutoff: str) -> datetime:
    """Parse an ISO 8601 cutoff into a timezone-aware market instant."""
    try:
        parsed = datetime.fromisoformat(explicit_cutoff)
    except ValueError as error:
        raise AppQueryError(
            "explicit_cutoff must be an ISO 8601 date or datetime"
        ) from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_MARKET_TZ)
    return parsed.astimezone(_MARKET_TZ)


def _attach_known_at(
    *,
    frame: pl.DataFrame,
    known_at_policy: KnownAtPolicy,
    explicit_cutoff: str | None,
) -> pl.DataFrame:
    if known_at_policy == KnownAtPolicy.EXPLICIT_CUTOFF:
        if explicit_cutoff is None:
            raise AppQueryError(
                "explicit_cutoff is required when "
                + "known_at_policy is explicit_cutoff"
            )
        return frame.with_columns(
            pl.lit(_parse_cutoff(explicit_cutoff)).alias("known_at")
        )
    return frame.with_columns(_sample_instant(pl.col("trade_date")).alias("known_at"))


def _source_instant(column: str, source_frame: pl.DataFrame) -> pl.Expr:
    """Availability at full timestamp precision; conservative for date-only values."""
    dtype = source_frame.schema[column]
    if dtype == pl.Date:
        return _end_of_day_instant(pl.col(column))
    if isinstance(dtype, pl.Datetime):
        expr = pl.col(column).cast(pl.Datetime("us"))
        if dtype.time_zone is None:
            return expr.dt.replace_time_zone(_MARKET_TZ_NAME)
        return expr.dt.convert_time_zone(_MARKET_TZ_NAME)
    text = (
        pl.col(column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace(" ", "T")
        .str.replace("Z$", "+00:00")
    )
    exact = pl.coalesce(
        [
            text.str.to_datetime(
                format="%Y-%m-%dT%H:%M:%S%.f%:z", strict=False
            ).dt.convert_time_zone(_MARKET_TZ_NAME),
            text.str.to_datetime(
                format="%Y-%m-%dT%H:%M:%S%.f", strict=False
            ).dt.replace_time_zone(_MARKET_TZ_NAME),
        ]
    )
    return (
        pl.when(text.str.len_bytes() > _DATE_ONLY_TEXT_WIDTH)
        .then(exact)
        .otherwise(_end_of_day_instant(text))
    )


def _pit_join(
    *,
    left_frame: pl.DataFrame,
    source_frame: pl.DataFrame,
    derived_id: str,
) -> pl.DataFrame:
    if source_frame.is_empty():
        return left_frame.with_columns(pl.lit(None).cast(pl.Float64).alias(derived_id))

    value_column = _source_value_column(source_frame)
    fallback_instant = _source_instant("trade_date", source_frame)
    if "availability_time" in source_frame.columns:
        declared_instant = _source_instant("availability_time", source_frame)
        declared = pl.col("availability_time")
        # A declared-but-unparseable value must fail closed, not fall back.
        declared_usable = declared.is_null() | declared_instant.is_not_null()
        availability_instant = pl.coalesce([declared_instant, fallback_instant])
    else:
        availability_instant = fallback_instant
        declared_usable = pl.lit(True)
    try:
        prepared_source = source_frame.select(
            pl.col("instrument_id").cast(pl.Int64),
            _date_column(pl.col("trade_date")).alias("source_trade_date"),
            availability_instant.alias("source_availability_time"),
            declared_usable.alias("_declared_usable"),
            pl.col(value_column).cast(pl.Float64).alias(derived_id),
        )
    except pl.exceptions.PolarsError as error:
        raise AppQueryError(
            "source availability_time is not a parseable date or timestamp"
        ) from error
    if prepared_source.filter(~pl.col("_declared_usable")).height:
        raise AppQueryError(
            "source availability_time is not a parseable date or timestamp"
        )
    prepared_source = prepared_source.drop("_declared_usable")
    if prepared_source["source_availability_time"].null_count():
        raise AppQueryError("source availability_time and trade_date are both missing")
    prepared_source = prepared_source.sort(
        ["instrument_id", "source_availability_time", "source_trade_date"]
    )

    joined = left_frame.sort(["instrument_id", "known_at", "trade_date"]).join_asof(
        prepared_source,
        left_on="known_at",
        right_on="source_availability_time",
        by="instrument_id",
        strategy="backward",
    )
    return joined.select([*left_frame.columns, derived_id]).sort("sample_row_id")


def _source_value_column(source_frame: pl.DataFrame) -> str:
    if "value" in source_frame.columns:
        return "value"
    key_columns = {"instrument_id", "trade_date", "availability_time"}
    for column in source_frame.columns:
        if column not in key_columns:
            return column
    raise DerivedValidationError(
        "source frame does not contain a research value column",
        field="columns",
        value=str(source_frame.columns),
        reason="no non-key column found to serve as research value",
    )


# ---------------------------------------------------------------------------
# Metadata / reporting helpers
# ---------------------------------------------------------------------------


def _build_dataset_report(
    *,
    dataset_frame: pl.DataFrame,
    derived_ids: tuple[str, ...],
    spine_row_count: int,
    snapshot_contract: _DatasetSnapshotContract,
) -> dict[str, object]:
    null_counts = _collect_null_counts(
        dataset_frame=dataset_frame,
        derived_ids=derived_ids,
    )
    return {
        "row_count": dataset_frame.height,
        "spine_row_count": spine_row_count,
        "null_counts": null_counts,
        "resolved_versions": snapshot_contract.resolved_versions,
        "known_at_policy": snapshot_contract.known_at_policy.value,
        "effective_cutoff": snapshot_contract.effective_cutoff,
        "source_snapshot_ids": list(snapshot_contract.source_snapshot_ids),
        "builder_version": snapshot_contract.builder_version,
    }


def _collect_null_counts(
    *,
    dataset_frame: pl.DataFrame,
    derived_ids: tuple[str, ...],
) -> dict[str, int]:
    if not derived_ids:
        return {}
    summary_frame = dataset_frame.select(
        [
            pl.col(derived_id).is_null().sum().alias(derived_id)
            for derived_id in derived_ids
        ]
    )
    summary_row = summary_frame.row(0, named=True)
    return {derived_id: int(summary_row[derived_id]) for derived_id in derived_ids}
