"""Derived catalog runtime metadata service."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ditto_datahub.models.derived import (
    DerivedCheckpointRecord,
    DerivedDependencyRecord,
    DerivedInvalidationRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)


class DerivedCatalogReaderProtocol(Protocol):
    """Reader protocol shared by file-based and SQLite-backed catalogs."""

    def has_any_records(self) -> bool:
        """Whether the backing catalog already contains runtime metadata."""
        ...

    def read_spec(self, derived_id: str, version: int) -> DerivedSpecRecord | None:
        """Read one derived spec record."""
        ...

    def read_version(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedVersionRecord | None:
        """Read one derived version record."""
        ...

    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]:
        """List all known versions for one derived id."""
        ...

    def read_run(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> DerivedRunRecord | None:
        """Read one run record."""
        ...

    def get_latest_run(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedRunRecord | None:
        """Read the latest run record for one derived version."""
        ...

    def read_state(self, derived_id: str) -> DerivedStateRecord | None:
        """Read the latest durable state record."""
        ...

    def list_partitions(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> list[DerivedPartitionRecord]:
        """List partition records for one run."""
        ...

    def list_checkpoints(
        self,
        derived_id: str,
        version: int,
    ) -> tuple[DerivedCheckpointRecord, ...]:
        """List checkpoint records for one derived version."""
        ...

    def list_dependencies_by_ref(
        self,
        dependency_ref: str,
    ) -> tuple[DerivedDependencyRecord, ...]:
        """List downstream dependency records for one upstream reference."""
        ...

    def list_pending_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List pending invalidation records."""
        ...

    def list_stale_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List stale invalidation records ordered by depth then created_at."""
        ...

    def list_specs(
        self,
        derived_ids: tuple[str, ...] | None = None,
        durable_only: bool = False,
    ) -> tuple[DerivedSpecRecord, ...]:
        """List active spec records."""
        ...


class DerivedCatalogWriterProtocol(Protocol):
    """Writer protocol shared by file-based and SQLite-backed catalogs."""

    def write_spec(self, record: DerivedSpecRecord) -> None:
        """Persist one derived spec record."""
        ...

    def write_version(self, record: DerivedVersionRecord) -> None:
        """Persist one derived version record."""
        ...

    def write_run(self, record: DerivedRunRecord) -> None:
        """Persist one run record."""
        ...

    def write_state(self, record: DerivedStateRecord) -> None:
        """Persist the latest durable state record."""
        ...

    def write_partitions(
        self,
        records: tuple[DerivedPartitionRecord, ...],
    ) -> None:
        """Persist partition records."""
        ...

    def write_checkpoints(
        self,
        records: tuple[DerivedCheckpointRecord, ...],
    ) -> None:
        """Persist checkpoint records."""
        ...

    def write_dependencies(
        self,
        records: tuple[DerivedDependencyRecord, ...],
    ) -> None:
        """Persist dependency records."""
        ...

    def write_invalidations(
        self,
        records: tuple[DerivedInvalidationRecord, ...],
    ) -> None:
        """Persist invalidation records."""
        ...

    def mark_invalidation_processed(
        self,
        invalidation_id: str,
        processed_at: str,
    ) -> None:
        """Mark one invalidation record as processed."""
        ...

    def mark_invalidation_status(
        self,
        invalidation_id: str,
        status: str,
    ) -> None:
        """Update the status of one invalidation record."""
        ...


class DerivedCatalogService:
    """Unified service for derived catalog runtime metadata."""

    def __init__(
        self,
        catalog_reader: DerivedCatalogReaderProtocol,
        catalog_writer: DerivedCatalogWriterProtocol,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._catalog_writer = catalog_writer

    def save_spec(self, record: DerivedSpecRecord) -> None:
        """Persist derived spec metadata."""
        self._catalog_writer.write_spec(record)

    def has_any_records(self) -> bool:
        """Whether the backing catalog already contains runtime metadata."""
        return self._catalog_reader.has_any_records()

    def get_spec(self, derived_id: str, version: int) -> DerivedSpecRecord | None:
        """Read derived spec metadata."""
        return self._catalog_reader.read_spec(derived_id, version)

    def save_version(self, record: DerivedVersionRecord) -> None:
        """Persist derived version metadata."""
        self._catalog_writer.write_version(record)

    def get_version(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedVersionRecord | None:
        """Read derived version metadata."""
        return self._catalog_reader.read_version(derived_id, version)

    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]:
        """List all version metadata for one derived id."""
        return self._catalog_reader.list_versions(derived_id)

    def save_run(self, record: DerivedRunRecord) -> None:
        """Persist derived run metadata."""
        self._catalog_writer.write_run(record)

    def get_run(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> DerivedRunRecord | None:
        """Read derived run metadata."""
        return self._catalog_reader.read_run(derived_id, version, run_id)

    def get_latest_run(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedRunRecord | None:
        """Return the latest run metadata for a version."""
        return self._catalog_reader.get_latest_run(derived_id, version)

    def save_state(self, record: DerivedStateRecord) -> None:
        """Persist latest state metadata."""
        self._catalog_writer.write_state(record)

    def get_state(self, derived_id: str) -> DerivedStateRecord | None:
        """Read latest state metadata."""
        return self._catalog_reader.read_state(derived_id)

    def save_partitions(self, records: tuple[DerivedPartitionRecord, ...]) -> None:
        """Persist partition metadata for a run."""
        self._catalog_writer.write_partitions(records)

    def list_partitions(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> list[DerivedPartitionRecord]:
        """List partition metadata for a run."""
        return self._catalog_reader.list_partitions(derived_id, version, run_id)

    def save_checkpoints(self, records: tuple[DerivedCheckpointRecord, ...]) -> None:
        """Persist checkpoint metadata."""
        self._catalog_writer.write_checkpoints(records)

    def list_checkpoints(
        self,
        derived_id: str,
        version: int,
    ) -> tuple[DerivedCheckpointRecord, ...]:
        """List checkpoint metadata."""
        return self._catalog_reader.list_checkpoints(derived_id, version)

    def save_dependencies(self, records: tuple[DerivedDependencyRecord, ...]) -> None:
        """Persist dependency edges."""
        self._catalog_writer.write_dependencies(records)

    def list_dependencies_by_ref(
        self,
        dependency_ref: str,
    ) -> tuple[DerivedDependencyRecord, ...]:
        """List downstream dependencies for one upstream reference."""
        return self._catalog_reader.list_dependencies_by_ref(dependency_ref)

    def list_downstream_dependencies(
        self,
        derived_id: str,
    ) -> tuple[DerivedDependencyRecord, ...]:
        """List downstream dependencies for one derived id used as upstream."""
        return self._catalog_reader.list_dependencies_by_ref(derived_id)

    def save_invalidations(
        self,
        records: tuple[DerivedInvalidationRecord, ...],
    ) -> None:
        """Persist invalidation rows."""
        self._catalog_writer.write_invalidations(records)

    def list_pending_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List invalidations waiting for repair."""
        return self._catalog_reader.list_pending_invalidations()

    def list_stale_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List stale invalidations ordered by depth then created_at."""
        return self._catalog_reader.list_stale_invalidations()

    def mark_invalidation_processed(
        self,
        invalidation_id: str,
        processed_at: str,
    ) -> None:
        """Mark one invalidation row as processed."""
        self._catalog_writer.mark_invalidation_processed(invalidation_id, processed_at)

    def mark_invalidation_status(
        self,
        invalidation_id: str,
        status: str,
    ) -> None:
        """Update the status of one invalidation row."""
        self._catalog_writer.mark_invalidation_status(invalidation_id, status)

    def list_specs(
        self,
        derived_ids: Sequence[str] | None = None,
        durable_only: bool = False,
    ) -> tuple[DerivedSpecRecord, ...]:
        """List active specs known to the backing catalog."""
        if derived_ids is None:
            return self._catalog_reader.list_specs(durable_only=durable_only)
        return self._catalog_reader.list_specs(
            derived_ids=tuple(derived_ids),
            durable_only=durable_only,
        )
