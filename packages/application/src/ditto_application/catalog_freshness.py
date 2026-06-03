"""Catalog freshness policy helpers shared by application read/process paths."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    default_dataset_metadata,
)

type CatalogFreshnessStatus = Literal[
    "fresh",
    "stale",
    "missing",
    "not_applicable",
]

__all__ = [
    "CatalogFreshnessAssessment",
    "CatalogFreshnessStatus",
    "assess_catalog_freshness",
    "catalog_entry_for_date",
    "catalog_repair_priority",
    "dataset_namespace",
    "latest_catalog_entry_for_dataset",
    "select_ingestion_source",
]


@dataclass(frozen=True, slots=True)
class CatalogFreshnessAssessment:
    """Freshness assessment for one dataset catalog entry."""

    status: CatalogFreshnessStatus
    sla_hours: int | None
    entry: DataCatalogEntry | None = None


def assess_catalog_freshness(
    *,
    dataset: str,
    catalog_entry: DataCatalogEntry | None,
    now: Callable[[], datetime] | None = None,
) -> CatalogFreshnessAssessment:
    """Assess a catalog entry against the data-owned dataset freshness SLA."""
    metadata = default_dataset_metadata().get(dataset)
    freshness_sla_hours = metadata.freshness_sla_hours if metadata is not None else None
    if freshness_sla_hours is None:
        return CatalogFreshnessAssessment(
            status="not_applicable",
            sla_hours=None,
            entry=catalog_entry,
        )
    if catalog_entry is None:
        return CatalogFreshnessAssessment(
            status="missing",
            sla_hours=freshness_sla_hours,
        )

    freshness_age = _ensure_aware_utc((now or _utcnow)()) - _ensure_aware_utc(
        catalog_entry.freshness_at
    )
    status: CatalogFreshnessStatus = (
        "fresh" if freshness_age <= timedelta(hours=freshness_sla_hours) else "stale"
    )
    return CatalogFreshnessAssessment(
        status=status,
        sla_hours=freshness_sla_hours,
        entry=catalog_entry,
    )


def latest_catalog_entry_for_dataset(
    reader: DataCatalogReader,
    dataset: str,
) -> DataCatalogEntry | None:
    """Return the freshest known catalog entry for a dataset."""
    entries = (
        entry for entry in reader.list_assets() if entry.asset.dataset_id == dataset
    )
    return max(entries, key=_catalog_entry_freshness_sort_key, default=None)


def catalog_entry_for_date(
    *,
    reader: DataCatalogReader,
    dataset: str,
    source: str,
    trade_date: str,
) -> DataCatalogEntry | None:
    """Return an exact-date catalog entry for dataset/source if present."""
    entry = reader.get_asset(
        DataAssetRef(
            dataset_id=dataset,
            namespace=dataset_namespace(dataset),
            partition_keys=(f"trade_date={trade_date}",),
        )
    )
    if entry is None or entry.source != source:
        return None
    return entry


def catalog_repair_priority(
    *,
    reader: DataCatalogReader,
    dataset: str,
    source: str,
    trade_date: str,
    now: Callable[[], datetime] | None = None,
) -> int:
    """Return lower values for failed dates that should be repaired first."""
    entry = catalog_entry_for_date(
        reader=reader,
        dataset=dataset,
        source=source,
        trade_date=trade_date,
    )
    assessment = assess_catalog_freshness(
        dataset=dataset,
        catalog_entry=entry,
        now=now,
    )
    return {
        "missing": 0,
        "stale": 1,
        "not_applicable": 2,
        "fresh": 3,
    }[assessment.status]


def select_ingestion_source(
    *,
    dataset: str,
    trade_date: str,
    available_sources: tuple[str, ...],
    catalog_reader: DataCatalogReader | None = None,
    now: Callable[[], datetime] | None = None,
) -> str:
    """Select the runtime source that should drive this ingestion request."""
    normalized_sources = tuple(
        dict.fromkeys(source.lower() for source in available_sources)
    )
    if not normalized_sources:
        msg = "available_sources must not be empty"
        raise ValueError(msg)

    metadata = default_dataset_metadata().get(dataset)
    supported_sources = (
        metadata.supported_sources if metadata is not None else normalized_sources
    )
    candidates = tuple(
        source for source in supported_sources if source in normalized_sources
    )
    if not candidates:
        return normalized_sources[0]

    default_source = (
        metadata.default_source
        if metadata is not None and metadata.default_source in candidates
        else candidates[0]
    )
    if catalog_reader is None:
        return default_source

    assessments = tuple(
        (
            source,
            assess_catalog_freshness(
                dataset=dataset,
                catalog_entry=catalog_entry_for_date(
                    reader=catalog_reader,
                    dataset=dataset,
                    source=source,
                    trade_date=trade_date,
                ),
                now=now,
            ),
        )
        for source in candidates
    )
    for status in ("fresh", "missing", "stale", "not_applicable"):
        for source, assessment in assessments:
            if assessment.status == status:
                return source
    return default_source


def dataset_namespace(dataset: str) -> str:
    """Return the catalog namespace for a known dataset."""
    metadata = default_dataset_metadata().get(dataset)
    if metadata is None:
        return "data"
    return metadata.domain


def _catalog_entry_freshness_sort_key(
    entry: DataCatalogEntry,
) -> tuple[datetime, str, str, tuple[str, ...]]:
    return (
        _ensure_aware_utc(entry.freshness_at),
        entry.storage_uri,
        entry.asset.namespace,
        entry.asset.partition_keys,
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
