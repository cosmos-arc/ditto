"""
Research catalog Protocol 定义（包内循环依赖隔离）.

Protocols 引用 research.domain 的 Record 类型，放在 research/ 包内
避免 contracts.py → research.domain → research.catalog_service → contracts.py 循环。
"""

from typing import Protocol, runtime_checkable

from ditto_analysis.research.domain import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)

__all__ = [
    "ResearchCatalogReaderProtocol",
    "ResearchCatalogWriterProtocol",
]


@runtime_checkable
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


@runtime_checkable
class ResearchCatalogWriterProtocol(Protocol):
    """
    Writer protocol for research catalog persistence.

    Each ``write_*`` method executes SQL and immediately commits.
    For batch operations requiring a single transaction, use the
    ``execute_*`` methods together with ``commit()`` / ``rollback()``.
    """

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...

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
