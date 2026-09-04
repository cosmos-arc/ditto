"""Catalog freshness policy helpers shared by application read/process paths."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Literal, Protocol

import orjson
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    default_dataset_metadata,
)
from ditto_data.models.ingestion import IngestionLog, IngestionStatus

type CatalogFreshnessStatus = Literal[
    "fresh",
    "stale",
    "missing",
    "not_applicable",
]

__all__ = [
    "CatalogAsOfSnapshot",
    "CatalogFreshnessAssessment",
    "CatalogFreshnessStatus",
    "PersistedIngestionEvidenceVerifier",
    "aggregate_source_snapshot_ids",
    "assess_catalog_freshness",
    "catalog_asof_snapshot",
    "catalog_entry_for_date",
    "catalog_repair_priority",
    "catalog_snapshot_has_quality_logs",
    "catalog_source_snapshot_id",
    "dataset_namespace",
    "latest_catalog_entry_for_dataset",
    "latest_catalog_entry_on_or_before",
    "select_ingestion_source",
]


class _IngestionLogReader(Protocol):
    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None: ...


@dataclass(frozen=True, slots=True)
class CatalogFreshnessAssessment:
    """Freshness assessment for one dataset catalog entry."""

    status: CatalogFreshnessStatus
    sla_hours: int | None
    entry: DataCatalogEntry | None = None


@dataclass(frozen=True, slots=True)
class CatalogAsOfSnapshot:
    """Cumulative catalog provenance selected under a signal-date PIT cutoff."""

    effective_partition_date: str
    source_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    row_count: int
    freshness_sla_hours: int


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


def latest_catalog_entry_on_or_before(
    *,
    reader: DataCatalogReader,
    dataset: str,
    source: str,
    trade_date: str,
) -> DataCatalogEntry | None:
    """Return the latest exact-date source snapshot visible as of ``trade_date``."""
    candidates = _catalog_entries_on_or_before(
        reader=reader,
        dataset=dataset,
        source=source,
        trade_date=trade_date,
    )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (item[0], *_catalog_entry_freshness_sort_key(item[1])),
    )[1]


def catalog_asof_snapshot(  # noqa: PLR0911 - fail-closed evidence validation
    *,
    reader: DataCatalogReader,
    dataset: str,
    source: str,
    signal_date: str,
) -> CatalogAsOfSnapshot | None:
    """Aggregate all persisted deltas visible at D under the dataset PIT SLA."""
    try:
        cutoff = date.fromisoformat(signal_date)
    except ValueError:
        return None
    dated_entries = _catalog_entries_on_or_before(
        reader=reader,
        dataset=dataset,
        source=source,
        trade_date=signal_date,
    )
    metadata = default_dataset_metadata().get(dataset)
    sla_hours = metadata.freshness_sla_hours if metadata is not None else None
    if not dated_entries or sla_hours is None:
        return None

    effective_date = max(item[0] for item in dated_entries)
    if (cutoff - effective_date).days * 24 > sla_hours:
        return None

    entries = tuple(item[1] for item in dated_entries)
    if any(
        not _is_l1_l2_attested_snapshot_id(entry.source_snapshot_id)
        for entry in entries
    ):
        return None
    snapshot_ids = tuple(
        sorted(
            {
                entry.source_snapshot_id
                for entry in entries
                if isinstance(entry.source_snapshot_id, str)
                and entry.source_snapshot_id
            }
        )
    )
    if len(snapshot_ids) != len(entries):
        return None
    row_counts = tuple(entry.schema.row_count for entry in entries)
    if any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in row_counts
    ):
        return None
    aggregate_id = aggregate_source_snapshot_ids(snapshot_ids)
    if aggregate_id is None:
        return None
    return CatalogAsOfSnapshot(
        effective_partition_date=effective_date.isoformat(),
        source_snapshot_id=aggregate_id,
        source_snapshot_ids=snapshot_ids,
        row_count=sum(count for count in row_counts if isinstance(count, int)),
        freshness_sla_hours=sla_hours,
    )


def aggregate_source_snapshot_ids(snapshot_ids: tuple[str, ...]) -> str | None:
    """Build the stable aggregate ID shared by PIT ingestion evidence."""
    normalized = tuple(sorted(set(snapshot_ids)))
    if not normalized:
        return None
    if len(normalized) == 1:
        return normalized[0]
    digest = sha256(orjson.dumps(normalized)).hexdigest()
    return f"snapshot-set:sha256:{digest}"


def catalog_source_snapshot_id(
    *,
    dataset: str,
    trade_date: str,
    source: str,
    checksum: str,
    l1_l2_attested: bool = False,
) -> str:
    """Build the canonical source snapshot ID for one date-level write."""
    snapshot_id = f"snapshot:{source}:{dataset}:{trade_date}:{checksum}"
    if l1_l2_attested:
        return f"{snapshot_id}:quality=l1-l2"
    return snapshot_id


def _is_l1_l2_attested_snapshot_id(snapshot_id: str | None) -> bool:
    return isinstance(snapshot_id, str) and snapshot_id.endswith("quality=l1-l2")


@dataclass(frozen=True, slots=True)
class PersistedIngestionEvidenceVerifier:
    """Bind serialized ingestion evidence to durable catalog and log facts."""

    reader: DataCatalogReader
    ingestion_logs: _IngestionLogReader

    def verify_exact_date(
        self,
        *,
        dataset: str,
        source: str,
        trade_date: str,
        checksum: str,
        row_count: int,
    ) -> bool:
        """Verify one non-sparse result against its DQ-attested persisted write."""
        entry = catalog_entry_for_date(
            reader=self.reader,
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )
        log = self.ingestion_logs.get_log(
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )
        return bool(
            entry is not None
            and log is not None
            and log.status == IngestionStatus.SUCCESS
            and log.checksum == checksum
            and log.rows == row_count
            and entry.schema.row_count == row_count
            and entry.source_snapshot_id
            == _expected_catalog_source_snapshot_id(
                entry=entry,
                dataset=dataset,
                source=source,
                checksum=checksum,
            )
        )

    def verify_asof_snapshot(
        self,
        *,
        dataset: str,
        source: str,
        signal_date: str,
        expected_snapshot_ids: tuple[str, ...],
        expected_row_count: int,
    ) -> bool:
        """Verify every component of one cumulative sparse PIT snapshot."""
        return catalog_snapshot_has_quality_logs(
            reader=self.reader,
            ingestion_logs=self.ingestion_logs,
            dataset=dataset,
            source=source,
            signal_date=signal_date,
            expected_snapshot_ids=expected_snapshot_ids,
            expected_row_count=expected_row_count,
        )


def catalog_snapshot_has_quality_logs(
    *,
    reader: DataCatalogReader,
    ingestion_logs: _IngestionLogReader,
    dataset: str,
    source: str,
    signal_date: str,
    expected_snapshot_ids: tuple[str, ...],
    expected_row_count: int,
) -> bool:
    """Verify every cumulative PIT catalog delta against a successful DQ-gated log."""
    dated_entries = _catalog_entries_on_or_before(
        reader=reader,
        dataset=dataset,
        source=source,
        trade_date=signal_date,
    )
    entries = tuple(item[1] for item in dated_entries)
    actual_ids = tuple(
        sorted(
            entry.source_snapshot_id
            for entry in entries
            if isinstance(entry.source_snapshot_id, str) and entry.source_snapshot_id
        )
    )
    if actual_ids != expected_snapshot_ids or len(entries) != len(actual_ids):
        return False
    row_count = 0
    for _partition_date, entry in dated_entries:
        log_trade_date = _catalog_log_trade_date(entry)
        if log_trade_date is None:
            return False
        log = ingestion_logs.get_log(
            dataset=dataset,
            source=source,
            trade_date=log_trade_date,
        )
        if (
            log is None
            or log.status != IngestionStatus.SUCCESS
            or not isinstance(log.checksum, str)
            or not log.checksum
            or not isinstance(log.rows, int)
            or isinstance(log.rows, bool)
            or log.rows < 0
            or log.rows != entry.schema.row_count
            or entry.source_snapshot_id
            != _expected_catalog_source_snapshot_id(
                entry=entry,
                dataset=dataset,
                source=source,
                checksum=log.checksum,
            )
        ):
            return False
        row_count += log.rows
    return row_count == expected_row_count


def _catalog_partition_values(entry: DataCatalogEntry) -> dict[str, str] | None:
    values: dict[str, str] = {}
    for partition in entry.asset.partition_keys:
        key, separator, value = partition.partition("=")
        if not separator or not key or not value or key in values:
            return None
        values[key] = value
    return values


def _catalog_log_trade_date(entry: DataCatalogEntry) -> str | None:
    values = _catalog_partition_values(entry)
    if values is None:
        return None
    if set(values) == {"trade_date"}:
        return values["trade_date"]
    if set(values) in (
        {"start_date", "end_date"},
        {"source_ticker", "start_date", "end_date"},
    ):
        return values["start_date"]
    return None


def _expected_catalog_source_snapshot_id(
    *,
    entry: DataCatalogEntry,
    dataset: str,
    source: str,
    checksum: str,
) -> str | None:
    values = _catalog_partition_values(entry)
    if values is None:
        return None
    if set(values) == {"trade_date"}:
        return catalog_source_snapshot_id(
            dataset=dataset,
            trade_date=values["trade_date"],
            source=source,
            checksum=checksum,
            l1_l2_attested=True,
        )
    if set(values) in (
        {"start_date", "end_date"},
        {"source_ticker", "start_date", "end_date"},
    ):
        source_ticker = values.get("source_ticker", "all")
        return (
            f"snapshot:{source}:{dataset}:{source_ticker}:"
            f"{values['start_date']}:{values['end_date']}:"
            f"{checksum}:quality=l1-l2"
        )
    return None


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


def _exact_partition_date(entry: DataCatalogEntry) -> date | None:
    trade_dates = [
        partition.removeprefix("trade_date=")
        for partition in entry.asset.partition_keys
        if partition.startswith("trade_date=")
    ]
    range_end_dates = [
        partition.removeprefix("end_date=")
        for partition in entry.asset.partition_keys
        if partition.startswith("end_date=")
    ]
    raw_dates = trade_dates or range_end_dates
    if len(raw_dates) != 1 or (trade_dates and range_end_dates):
        return None
    try:
        return date.fromisoformat(raw_dates[0])
    except ValueError:
        return None


def _catalog_entries_on_or_before(
    *,
    reader: DataCatalogReader,
    dataset: str,
    source: str,
    trade_date: str,
) -> tuple[tuple[date, DataCatalogEntry], ...]:
    try:
        cutoff = date.fromisoformat(trade_date)
    except ValueError:
        return ()
    namespace = dataset_namespace(dataset)
    candidates: list[tuple[date, DataCatalogEntry]] = []
    for entry in reader.list_assets(namespace):
        if entry.asset.dataset_id != dataset or entry.source != source:
            continue
        partition_date = _exact_partition_date(entry)
        if partition_date is not None and partition_date <= cutoff:
            candidates.append((partition_date, entry))
    return tuple(candidates)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
