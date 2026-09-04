"""Fail-closed point-in-time query identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["DatasetSnapshot", "PITQueryContext"]


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"Invalid PIT {field}: {value!r}")


def _validate_aware(field: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"PIT {field} must be timezone-aware")


@dataclass(frozen=True)
class DatasetSnapshot:
    """Exact source snapshots and schema version visible for one dataset."""

    dataset_id: str
    dataset_version: str
    source_snapshot_ids: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        """Reject ambiguous or mutable dataset identities."""
        _validate_text("dataset_id", self.dataset_id)
        _validate_text("dataset_version", self.dataset_version)
        _validate_aware("dataset snapshot created_at", self.created_at)
        if not self.source_snapshot_ids or len(set(self.source_snapshot_ids)) != len(
            self.source_snapshot_ids
        ):
            raise ValueError("PIT dataset snapshot requires unique source_snapshot_ids")
        for snapshot_id in self.source_snapshot_ids:
            _validate_text("source_snapshot_id", snapshot_id)


@dataclass(frozen=True)
class PITQueryContext:
    """All visibility boundaries required for a historical or live decision."""

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshots: tuple[DatasetSnapshot, ...]

    def __post_init__(self) -> None:
        """Validate time ordering and exact dataset snapshot coverage."""
        for field in ("as_of", "knowledge_cutoff", "publication_cutoff"):
            _validate_aware(field, getattr(self, field))
        if self.publication_cutoff > self.knowledge_cutoff:
            raise ValueError("PIT publication_cutoff exceeds knowledge_cutoff")
        if self.knowledge_cutoff > self.as_of:
            raise ValueError("PIT knowledge_cutoff exceeds as_of")
        if not self.source_snapshots:
            raise ValueError("PIT context requires at least one source snapshot")
        dataset_ids = tuple(snapshot.dataset_id for snapshot in self.source_snapshots)
        if len(set(dataset_ids)) != len(dataset_ids):
            raise ValueError("PIT context has duplicate dataset source snapshots")

    def snapshot_for(self, dataset_id: str) -> DatasetSnapshot:
        """Return the exact dataset snapshot or fail before any storage read."""
        _validate_text("dataset_id", dataset_id)
        for snapshot in self.source_snapshots:
            if snapshot.dataset_id == dataset_id:
                return snapshot
        raise ValueError(f"PIT context has no source snapshot for {dataset_id!r}")

    @property
    def source_snapshot_ids(self) -> tuple[str, ...]:
        """Flatten exact provider snapshot identities in declared dataset order."""
        return tuple(
            snapshot_id
            for snapshot in self.source_snapshots
            for snapshot_id in snapshot.source_snapshot_ids
        )
