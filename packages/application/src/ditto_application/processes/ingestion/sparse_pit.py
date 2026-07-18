"""Sparse PIT ingestion cutoff and cumulative snapshot evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

import polars as pl
from ditto_data.catalog import DataCatalogReader
from ditto_data.models.ingestion import IngestionSnapshotEvidence

from ditto_application.catalog_freshness import catalog_asof_snapshot

type SparsePITCutoffError = Literal[
    "PIT_CUTOFF_DATE_INVALID",
    "PIT_KNOWLEDGE_DATE_MISSING",
    "PIT_KNOWLEDGE_DATE_INVALID",
    "PIT_KNOWLEDGE_DATE_AFTER_CUTOFF",
]

__all__ = [
    "SparsePITCutoffError",
    "is_sparse_pit_dataset",
    "resolve_sparse_asof_snapshot",
    "validate_sparse_pit_cutoff",
]

_SPARSE_PIT_DATASETS: frozenset[str] = frozenset(
    {
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "dividend",
        "corporate_actions",
        "index_weight",
    }
)


def is_sparse_pit_dataset(dataset: str) -> bool:
    """Return whether a dataset is represented as cumulative sparse PIT deltas."""
    return dataset in _SPARSE_PIT_DATASETS


def validate_sparse_pit_cutoff(
    df: pl.DataFrame,
    *,
    dataset: str,
    trade_date: str,
) -> SparsePITCutoffError | None:
    """Reject sparse rows that were not knowable by the requested PIT cutoff."""
    if not is_sparse_pit_dataset(dataset):
        return None
    try:
        cutoff = date.fromisoformat(trade_date)
    except ValueError:
        return "PIT_CUTOFF_DATE_INVALID"
    knowledge_date_column = (
        "effective_from" if dataset == "index_weight" else "knowledge_date"
    )
    if knowledge_date_column not in df.columns:
        return "PIT_KNOWLEDGE_DATE_MISSING"

    raw_dates = df.get_column(knowledge_date_column)
    if raw_dates.null_count() > 0:
        return "PIT_KNOWLEDGE_DATE_INVALID"
    knowledge_dates = _normalized_knowledge_dates(raw_dates)
    if knowledge_dates is None:
        return "PIT_KNOWLEDGE_DATE_INVALID"

    return (
        "PIT_KNOWLEDGE_DATE_AFTER_CUTOFF" if knowledge_dates.gt(cutoff).any() else None
    )


def _normalized_knowledge_dates(raw_dates: pl.Series) -> pl.Series | None:
    try:
        if raw_dates.dtype == pl.Date:
            return raw_dates
        if isinstance(raw_dates.dtype, pl.Datetime):
            return raw_dates.dt.date()
        if raw_dates.dtype == pl.String:
            return raw_dates.str.to_date(strict=True)
    except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError):
        return None
    return None


def resolve_sparse_asof_snapshot(
    *,
    dataset: str,
    trade_date: str,
    source_name: str,
    catalog_reader: DataCatalogReader | None,
) -> IngestionSnapshotEvidence | None:
    """Resolve durable cumulative PIT provenance at the signal-date cutoff."""
    if catalog_reader is None:
        return None
    snapshot = catalog_asof_snapshot(
        reader=catalog_reader,
        dataset=dataset,
        source=source_name,
        signal_date=trade_date,
    )
    if snapshot is None:
        return None
    return IngestionSnapshotEvidence(
        kind="persisted_asof_catalog_snapshot",
        source=source_name,
        signal_date=trade_date,
        checked_at=datetime.now(UTC).isoformat(),
        effective_partition_date=snapshot.effective_partition_date,
        source_snapshot_id=snapshot.source_snapshot_id,
        source_snapshot_ids=snapshot.source_snapshot_ids,
        row_count=snapshot.row_count,
        freshness_sla_hours=snapshot.freshness_sla_hours,
    )
