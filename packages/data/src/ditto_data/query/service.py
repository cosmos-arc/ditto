"""Snapshot-bound Polars query facade with strict PIT visibility filtering."""

from __future__ import annotations

from datetime import UTC
from typing import Protocol, runtime_checkable

import polars as pl

from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext

__all__ = ["PITDatasetReader", "PITQueryService"]

_REQUIRED_COLUMNS = frozenset(
    {
        "event_time",
        "published_at",
        "available_at",
        "source_snapshot_id",
        "dataset_version",
    }
)


@runtime_checkable
class PITDatasetReader(Protocol):
    """Read only the immutable dataset snapshot supplied by the query context."""

    def read_dataset(self, snapshot: DatasetSnapshot) -> pl.DataFrame:
        """Return normalized rows for one exact dataset snapshot."""
        ...


class PITQueryService:
    """Apply common time and lineage visibility rules to normalized data."""

    def __init__(self, reader: PITDatasetReader) -> None:
        self._reader = reader

    def query(
        self,
        *,
        dataset_id: str,
        context: PITQueryContext,
    ) -> pl.DataFrame:
        """Read an exact snapshot and exclude anything not visible at cutoff."""
        snapshot = context.snapshot_for(dataset_id)
        frame = self._reader.read_dataset(snapshot)
        missing = _REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            raise ValueError(
                f"dataset {dataset_id!r} lacks required PIT columns: {sorted(missing)}"
            )
        for column in _REQUIRED_COLUMNS:
            if frame.get_column(column).null_count() > 0:
                raise ValueError(
                    f"dataset {dataset_id!r} has null PIT field {column!r}"
                )

        source_ids = set(
            frame.get_column("source_snapshot_id").cast(pl.String).unique().to_list()
        )
        versions = set(
            frame.get_column("dataset_version").cast(pl.String).unique().to_list()
        )
        if not source_ids.issubset(snapshot.source_snapshot_ids) or versions != {
            snapshot.dataset_version
        }:
            raise ValueError(
                f"dataset {dataset_id!r} snapshot or version drifted from PIT context"
            )

        as_of = context.as_of.astimezone(UTC)
        publication_cutoff = context.publication_cutoff.astimezone(UTC)
        knowledge_cutoff = context.knowledge_cutoff.astimezone(UTC)
        try:
            return frame.filter(
                (pl.col("event_time") <= as_of)
                & (pl.col("published_at") <= publication_cutoff)
                & (pl.col("available_at") <= knowledge_cutoff)
            )
        except (
            pl.exceptions.InvalidOperationError,
            pl.exceptions.SchemaError,
        ) as error:
            raise ValueError(
                f"dataset {dataset_id!r} PIT time columns must be comparable datetimes"
            ) from error
