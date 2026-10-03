"""Source snapshot provenance resolution for derived materialization."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

import orjson
from ditto_data.catalog import DataCatalogReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_features.materialization.dependency_registry import (
    dependency_contracts,
)

from ditto_application.processes.materialization.catalog_dependency_validation import (
    validate_dependency_catalog_compatibility,
)
from ditto_application.processes.materialization.types import InputContext

__all__ = [
    "CatalogCoverageDatesProvider",
    "CatalogSourceSnapshotResolver",
    "SourceSnapshotProvenance",
    "SourceSnapshotResolver",
]

type CatalogCoverageDatesProvider = Callable[[str, str], Iterable[str]]


@dataclass(frozen=True)
class SourceSnapshotProvenance:
    """Resolved source snapshot aggregate plus exact selected source snapshots."""

    source_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...] = ()

    @classmethod
    def from_ids(cls, snapshot_ids: Iterable[str | None]) -> SourceSnapshotProvenance:
        """Build stable aggregate provenance from exact source snapshot IDs."""
        normalized = _normalize_snapshot_ids(snapshot_ids)
        return cls(
            source_snapshot_id=_aggregate_snapshot_id(normalized),
            source_snapshot_ids=normalized,
        )


class SourceSnapshotResolver(Protocol):
    """Resolve source snapshot provenance for one materialization input context."""

    def resolve(self, context: InputContext) -> SourceSnapshotProvenance:
        """Return the source snapshots selected for the materialization inputs."""
        ...


class CatalogSourceSnapshotResolver:
    """Resolve selected source snapshots from completed snapshot coverage facts."""

    def __init__(
        self,
        *,
        data_catalog_reader: DataCatalogReader,
        snapshots: ProviderSnapshotReader,
        lifecycle: PartitionLifecycleReader,
        catalog_coverage_dates_provider: CatalogCoverageDatesProvider | None = None,
    ) -> None:
        self._data_catalog_reader = data_catalog_reader
        self._snapshots = snapshots
        self._lifecycle = lifecycle
        self._catalog_coverage_dates_provider = catalog_coverage_dates_provider

    def resolve(self, context: InputContext) -> SourceSnapshotProvenance:
        """Return snapshot-fact provenance for *context*."""
        plan = context.plan
        required_dates = self._catalog_required_dates(
            start=str(plan.compute_start),
            end=str(plan.compute_end),
        )
        report = validate_dependency_catalog_compatibility(
            contracts=dependency_contracts(context.dependencies),
            catalog_reader=self._data_catalog_reader,
            snapshots=self._snapshots,
            lifecycle=self._lifecycle,
            required_dates=required_dates,
            expected_source_snapshot_id=context.request.source_snapshot_id,
        )
        if report.source_snapshot_ids:
            return SourceSnapshotProvenance.from_ids(report.source_snapshot_ids)
        return SourceSnapshotProvenance.from_ids((context.request.source_snapshot_id,))

    def _catalog_required_dates(self, *, start: str, end: str) -> tuple[str, ...]:
        if self._catalog_coverage_dates_provider is None:
            return ()
        return tuple(self._catalog_coverage_dates_provider(start, end))


def _normalize_snapshot_ids(snapshot_ids: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(sorted({snapshot_id for snapshot_id in snapshot_ids if snapshot_id}))


def _aggregate_snapshot_id(snapshot_ids: tuple[str, ...]) -> str | None:
    if len(snapshot_ids) == 0:
        return None
    if len(snapshot_ids) == 1:
        return snapshot_ids[0]
    digest = sha256(orjson.dumps(snapshot_ids)).hexdigest()
    return f"snapshot-set:sha256:{digest}"
