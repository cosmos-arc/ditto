"""Research control-plane metadata service."""

from __future__ import annotations

from typing import Protocol

from ditto_analytics.models.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)


class ResearchCatalogReaderProtocol(Protocol):
    """Reader protocol for research specs and snapshots."""

    def read_spine_spec(self, spine_id: str) -> ResearchSpineSpecRecord | None:
        """Read one spine spec record."""
        ...

    def read_dataset_spec(
        self,
        dataset_id: str,
    ) -> ResearchDatasetSpecRecord | None:
        """Read one dataset spec record."""
        ...

    def read_spine_snapshot(
        self,
        spine_snapshot_id: str,
    ) -> ResearchSpineSnapshotRecord | None:
        """Read one spine snapshot record."""
        ...

    def read_dataset_snapshot(
        self,
        snapshot_id: str,
    ) -> ResearchDatasetSnapshotRecord | None:
        """Read one dataset snapshot record."""
        ...

    def get_latest_spine_snapshot(
        self,
        spine_id: str,
    ) -> ResearchSpineSnapshotRecord | None:
        """Read the latest spine snapshot for one spine id."""
        ...

    def get_latest_dataset_snapshot(
        self,
        dataset_id: str,
    ) -> ResearchDatasetSnapshotRecord | None:
        """Read the latest dataset snapshot for one dataset id."""
        ...


class ResearchCatalogWriterProtocol(Protocol):
    """
    Writer protocol for research catalog persistence.

    Each ``write_*`` method executes SQL and immediately commits.
    For batch operations requiring a single transaction, use the
    ``execute_*`` methods together with ``commit()`` / ``rollback()``.
    """

    # --- transaction control ---

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...

    # --- execute methods (no commit) ---

    def execute_spine_spec(self, record: ResearchSpineSpecRecord) -> None:
        """Execute spine spec INSERT without committing."""
        ...

    def execute_dataset_spec(self, record: ResearchDatasetSpecRecord) -> None:
        """Execute dataset spec INSERT without committing."""
        ...

    def execute_spine_snapshot(self, record: ResearchSpineSnapshotRecord) -> None:
        """Execute spine snapshot INSERT without committing."""
        ...

    def execute_dataset_snapshot(self, record: ResearchDatasetSnapshotRecord) -> None:
        """Execute dataset snapshot INSERT without committing."""
        ...

    # --- write methods (execute + commit) ---

    def write_spine_spec(self, record: ResearchSpineSpecRecord) -> None:
        """Persist one spine spec record."""
        ...

    def write_dataset_spec(self, record: ResearchDatasetSpecRecord) -> None:
        """Persist one dataset spec record."""
        ...

    def write_spine_snapshot(self, record: ResearchSpineSnapshotRecord) -> None:
        """Persist one spine snapshot record."""
        ...

    def write_dataset_snapshot(
        self,
        record: ResearchDatasetSnapshotRecord,
    ) -> None:
        """Persist one dataset snapshot record."""
        ...


class ResearchCatalogService:
    """Unified service for research control-plane metadata."""

    def __init__(
        self,
        catalog_reader: ResearchCatalogReaderProtocol,
        catalog_writer: ResearchCatalogWriterProtocol,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._catalog_writer = catalog_writer

    def save_spine_spec(self, record: ResearchSpineSpecRecord) -> None:
        """Persist one spine spec record."""
        self._catalog_writer.write_spine_spec(record)

    def get_spine_spec(self, spine_id: str) -> ResearchSpineSpecRecord | None:
        """Read one spine spec record."""
        return self._catalog_reader.read_spine_spec(spine_id)

    def save_dataset_spec(self, record: ResearchDatasetSpecRecord) -> None:
        """Persist one dataset spec record."""
        self._catalog_writer.write_dataset_spec(record)

    def get_dataset_spec(
        self,
        dataset_id: str,
    ) -> ResearchDatasetSpecRecord | None:
        """Read one dataset spec record."""
        return self._catalog_reader.read_dataset_spec(dataset_id)

    def save_spine_snapshot(self, record: ResearchSpineSnapshotRecord) -> None:
        """Persist one spine snapshot record."""
        self._catalog_writer.write_spine_snapshot(record)

    def get_spine_snapshot(
        self,
        spine_snapshot_id: str,
    ) -> ResearchSpineSnapshotRecord | None:
        """Read one spine snapshot record."""
        return self._catalog_reader.read_spine_snapshot(spine_snapshot_id)

    def get_latest_spine_snapshot(
        self,
        spine_id: str,
    ) -> ResearchSpineSnapshotRecord | None:
        """Read the latest spine snapshot for one spine id."""
        return self._catalog_reader.get_latest_spine_snapshot(spine_id)

    def save_dataset_snapshot(self, record: ResearchDatasetSnapshotRecord) -> None:
        """Persist one dataset snapshot record."""
        self._catalog_writer.write_dataset_snapshot(record)

    def get_dataset_snapshot(
        self,
        snapshot_id: str,
    ) -> ResearchDatasetSnapshotRecord | None:
        """Read one dataset snapshot record."""
        return self._catalog_reader.read_dataset_snapshot(snapshot_id)

    def get_latest_dataset_snapshot(
        self,
        dataset_id: str,
    ) -> ResearchDatasetSnapshotRecord | None:
        """Read the latest dataset snapshot for one dataset id."""
        return self._catalog_reader.get_latest_dataset_snapshot(dataset_id)
