"""Exact immutable snapshot reads; never fall back to the mutable canonical asset."""

from dataclasses import dataclass
from datetime import date, datetime

import polars as pl

from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader


@dataclass(frozen=True, slots=True)
class SnapshotContents:
    """Pinned raw evidence for audit; qualification is a separate application check."""

    snapshot: ProviderSnapshot
    previous_snapshot_id: str | None
    observed_at: datetime | None
    frame: pl.DataFrame


class SnapshotReadService:
    """Read retained content only after its own ingestion completed."""

    def __init__(
        self,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        lifecycle: PartitionLifecycleReader,
    ) -> None:
        self._snapshots = snapshots
        self._payloads = payloads
        self._lifecycle = lifecycle

    def read(self, snapshot_id: str) -> SnapshotContents:
        """Verify the exact content identity and completion before reading bytes."""
        snapshot = self._snapshots.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.snapshot_id != snapshot.expected_snapshot_id():
            raise ValueError("provider snapshot is missing or has invalid identity")
        if not snapshot_completed(snapshot, self._lifecycle):
            raise ValueError("provider snapshot has no COMPLETE checkpoint")
        if not snapshot.payload_retained or snapshot.payload_uri is None:
            raise ValueError("provider snapshot has no retained payload")
        # Sharing one artifact across schema versions is legitimate when the
        # physical bytes are the schema; the payload read pins them via the
        # persisted schema fingerprint, so exactness is proven there.
        frame = self._payloads.read_payload(
            ProviderPayloadArtifact(
                dataset_id=snapshot.dataset_id,
                source=snapshot.source,
                checksum=snapshot.checksum,
                row_count=snapshot.row_count,
                uri=snapshot.payload_uri,
            )
        )
        return SnapshotContents(
            snapshot,
            self._snapshots.get_predecessor(snapshot_id),
            self._snapshots.get_observed_at(snapshot_id),
            frame,
        )

    def read_fields(
        self,
        snapshot_id: str,
        columns: tuple[str, ...],
        *,
        instrument_ids: tuple[int, ...],
        date_range: tuple[date, date],
    ) -> pl.DataFrame:
        """Project only the caller-qualified instrument, interval and field scope."""
        contents = self.read(snapshot_id)
        selected = tuple(dict.fromkeys(("instrument_id", "trade_date", *columns)))
        if not set(selected).issubset(contents.frame.columns):
            raise ValueError(
                "snapshot replay requires retained instrument/date/field columns"
            )
        return contents.frame.filter(
            pl.col("instrument_id").is_in(instrument_ids)
            & pl.col("trade_date").is_between(*date_range)
        ).select(selected)
