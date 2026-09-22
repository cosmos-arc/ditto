"""Shared provider-snapshot grouping for exact PIT query contexts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
)
from ditto_data.query.contracts import DatasetSnapshot

from ditto_application.exceptions import AppQueryError

__all__ = ["SnapshotGroupError", "group_dataset_snapshots"]


class SnapshotGroupError(Protocol):
    """Error factory each caller uses for its own fail-closed codes."""

    def __call__(self, code: str, reason: str, **details: object) -> AppQueryError:
        """Build one coded fail-closed error."""
        ...


def group_dataset_snapshots(
    snapshots: Sequence[ProviderSnapshot],
    *,
    error: SnapshotGroupError,
    mixed_version_code: str,
) -> tuple[DatasetSnapshot, ...]:
    """Group retained snapshots per dataset, rejecting mixed schema versions."""
    grouped: dict[str, list[ProviderSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.dataset_id, []).append(snapshot)
    result: list[DatasetSnapshot] = []
    for dataset_id, values in sorted(grouped.items()):
        versions = {item.schema_version for item in values}
        if len(versions) != 1:
            raise error(
                mixed_version_code,
                "snapshot set has mixed dataset versions",
                dataset_id=dataset_id,
            )
        result.append(
            DatasetSnapshot(
                dataset_id=dataset_id,
                dataset_version=next(iter(versions)),
                source_snapshot_ids=tuple(
                    item.snapshot_id
                    for item in sorted(values, key=lambda item: item.snapshot_id)
                ),
                created_at=max(item.created_at for item in values),
            )
        )
    return tuple(result)
