"""Research control-plane metadata service."""

from __future__ import annotations

from ditto_analysis.research.domain import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_analysis.research.protocols import (
    ResearchCatalogReaderProtocol,
    ResearchCatalogWriterProtocol,
)


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
