"""
Pure helper functions for research dataset snapshot construction.

Extracted from ``research.py`` to keep the facade focused on orchestration.
All symbols are private by convention (``_`` prefix) and consumed only by
``ResearchDatasetFacade``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import cast

import orjson
import polars as pl
from ditto_analysis.research.domain import (
    KnownAtPolicy,
    LateArrivalPolicy,
    ResearchDatasetSpec,
    ResearchDatasetSpecRecord,
    ResearchSpineSpecRecord,
    SpineSpec,
)
from ditto_features.errors import DerivedValidationError
from ditto_kernel.market import CalendarId, GrainId

from ditto_application.exceptions import AppQueryError

__all__ = [
    "_DatasetSnapshotContract",
    "_attach_known_at",
    "_build_dataset_report",
    "_coerce_date",
    "_collect_null_counts",
    "_hydrate_dataset_spec",
    "_hydrate_spine_spec",
    "_manifest_hash",
    "_normalize_trade_dates",
    "_pit_join",
    "_source_value_column",
]

# ---------------------------------------------------------------------------
# Shared frozen contract (used by facade methods *and* report builder)
# ---------------------------------------------------------------------------

_RESEARCH_BUILDER_VERSION = "unified-derived-research-v1"


@dataclass(frozen=True)
class _DatasetSnapshotContract:
    """Frozen contract payload persisted with each dataset snapshot."""

    known_at_policy: KnownAtPolicy
    effective_cutoff: str | None
    resolved_versions: dict[str, int]
    resolved_inputs: tuple[dict[str, str | int], ...]
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
    trade_dates = calendar_frame.select(
        pl.col("trade_date").cast(pl.Utf8).str.slice(0, 10).str.to_date()
    )
    return trade_dates


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
            pl.lit(_coerce_date(explicit_cutoff)).alias("known_at")
        )
    return frame.with_columns(pl.col("trade_date").alias("known_at"))


def _pit_join(
    *,
    left_frame: pl.DataFrame,
    source_frame: pl.DataFrame,
    derived_id: str,
) -> pl.DataFrame:
    if source_frame.is_empty():
        return left_frame.with_columns(pl.lit(None).cast(pl.Float64).alias(derived_id))

    value_column = _source_value_column(source_frame)
    prepared_source = source_frame.select(
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("trade_date")
        .cast(pl.Utf8)
        .str.slice(0, 10)
        .str.to_date()
        .alias("source_trade_date"),
        pl.coalesce(
            [
                pl.col("availability_time"),
                pl.col("trade_date"),
            ]
        )
        .cast(pl.Utf8)
        .str.slice(0, 10)
        .str.to_date()
        .alias("source_availability_time"),
        pl.col(value_column).cast(pl.Float64).alias(derived_id),
    ).sort(["instrument_id", "source_availability_time", "source_trade_date"])

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


def _manifest_hash(metadata: Mapping[str, object]) -> str:
    payload = orjson.dumps(metadata, option=orjson.OPT_SORT_KEYS)
    return sha256(payload).hexdigest()


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


def _coerce_date(value: str) -> date:
    return date.fromisoformat(value[:10])
