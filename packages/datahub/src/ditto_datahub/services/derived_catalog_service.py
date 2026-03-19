"""Derived catalog runtime metadata service."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import polars as pl

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
from ditto_datahub.services.derived.garbage_collector import DerivedGarbageCollector
from ditto_datahub.services.derived.gc_models import GcReport


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
        """List stale invalidation records ordered by role priority then depth."""
        ...

    def list_dead_letter_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List dead-letter invalidation records ordered by dead_letter_at."""
        ...

    def list_specs(
        self,
        derived_ids: tuple[str, ...] | None = None,
        durable_only: bool = False,
    ) -> tuple[DerivedSpecRecord, ...]:
        """List active spec records."""
        ...


class DerivedCatalogWriterProtocol(Protocol):
    """
    Writer protocol for derived catalog persistence.

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

    def execute_spec(self, record: DerivedSpecRecord) -> None:
        """Execute spec INSERT without committing."""
        ...

    def execute_version(self, record: DerivedVersionRecord) -> None:
        """Execute version INSERT without committing."""
        ...

    def execute_run(self, record: DerivedRunRecord) -> None:
        """Execute run INSERT without committing."""
        ...

    def execute_state(self, record: DerivedStateRecord) -> None:
        """Execute state INSERT without committing."""
        ...

    def execute_partitions(self, records: tuple[DerivedPartitionRecord, ...]) -> None:
        """Execute partition INSERTs without committing."""
        ...

    def execute_checkpoints(self, records: tuple[DerivedCheckpointRecord, ...]) -> None:
        """Execute checkpoint INSERTs without committing."""
        ...

    def execute_dependencies(
        self, records: tuple[DerivedDependencyRecord, ...]
    ) -> None:
        """Execute dependency INSERTs without committing."""
        ...

    def execute_invalidations(
        self, records: tuple[DerivedInvalidationRecord, ...]
    ) -> None:
        """Execute invalidation INSERTs without committing."""
        ...

    def execute_invalidation_processed(
        self, invalidation_id: str, processed_at: str
    ) -> None:
        """Execute invalidation processed UPDATE without committing."""
        ...

    def execute_invalidation_status(self, invalidation_id: str, status: str) -> None:
        """Execute invalidation status UPDATE without committing."""
        ...

    # --- write methods (execute + commit) ---

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

    def execute_increment_retry_count(self, invalidation_id: str) -> None:
        """Increment retry_count for one invalidation row without committing."""
        ...

    def execute_mark_invalidation_dead_letter(
        self, invalidation_id: str, error_message: str, dead_letter_at: str
    ) -> None:
        """Mark one invalidation as dead letter without committing."""
        ...

    def increment_retry_count(self, invalidation_id: str) -> None:
        """Increment retry_count for one invalidation row."""
        ...

    def mark_invalidation_dead_letter(
        self, invalidation_id: str, error_message: str, dead_letter_at: str
    ) -> None:
        """Mark one invalidation as dead letter."""
        ...

    # --- delete methods ---

    def delete_version_records(self, derived_id: str, version: int) -> int:
        """
        Delete all records for one derived version.

        Removes rows from derived_run, derived_partition,
        derived_checkpoint, derived_spec, and derived_version.

        Does NOT touch derived_state, derived_dependency, or
        derived_invalidation (managed separately).

        Returns the number of records removed.
        """
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

    def list_dead_letter_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List dead-letter invalidations ordered by dead_letter_at."""
        return self._catalog_reader.list_dead_letter_invalidations()

    def increment_retry_count(self, invalidation_id: str) -> None:
        """Increment retry_count for one invalidation row."""
        self._catalog_writer.increment_retry_count(invalidation_id)

    def mark_invalidation_dead_letter(
        self, invalidation_id: str, error_message: str, dead_letter_at: str
    ) -> None:
        """Mark one invalidation as dead letter."""
        self._catalog_writer.mark_invalidation_dead_letter(
            invalidation_id,
            error_message,
            dead_letter_at,
        )

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

    def catalog_dashboard(self) -> pl.DataFrame:
        """
        Return a unified catalog dashboard view.

        Joins spec, version, state, and latest-run metadata into a single
        monitoring/debugging DataFrame.  Returns an empty frame with the
        canonical schema when no specs exist.
        """
        specs = self._catalog_reader.list_specs(durable_only=False)
        if not specs:
            return _empty_dashboard()
        rows: list[dict[str, object]] = []
        for spec in specs:
            version_rec = self._catalog_reader.read_version(
                spec.derived_id, spec.version
            )
            state_rec = self._catalog_reader.read_state(spec.derived_id)
            run_rec = (
                self._catalog_reader.get_latest_run(spec.derived_id, spec.version)
                if version_rec is not None
                else None
            )
            rows.append(
                {
                    "derived_id": spec.derived_id,
                    "version": spec.version,
                    "role": spec.role,
                    "profile": spec.materialization_profile,
                    "version_status": version_rec.status if version_rec else None,
                    "is_online": version_rec.is_online if version_rec else None,
                    "is_primary": version_rec.is_primary if version_rec else None,
                    "active_version": (state_rec.active_version if state_rec else None),
                    "latest_run_id": run_rec.run_id if run_rec else None,
                    "latest_run_status": run_rec.status if run_rec else None,
                    "total_rows": state_rec.total_rows if state_rec else None,
                    "watermark": state_rec.watermark if state_rec else None,
                }
            )
        return pl.DataFrame(rows, schema=_dashboard_schema())

    # --- garbage collection ---

    def gc_versions(
        self,
        derived_id: str,
        artifact_root: Path | str,
        keep_last_n: int = 3,
    ) -> GcReport:
        """
        Execute GC for one derived id.

        Delegates to
        :class:`~ditto_datahub.services.derived.garbage_collector.DerivedGarbageCollector`.
        """
        gc = DerivedGarbageCollector(
            catalog_reader=self._catalog_reader,
            catalog_writer=self._catalog_writer,
            artifact_root=Path(artifact_root),
        )
        return gc.gc_versions(derived_id, keep_last_n=keep_last_n)

    def gc_all(
        self,
        artifact_root: Path | str,
        keep_last_n: int = 3,
    ) -> list[GcReport]:
        """
        Execute GC for every derived id known to the catalog.

        Delegates to
        :class:`~ditto_datahub.services.derived.garbage_collector.DerivedGarbageCollector`.
        """
        gc = DerivedGarbageCollector(
            catalog_reader=self._catalog_reader,
            catalog_writer=self._catalog_writer,
            artifact_root=Path(artifact_root),
        )
        return gc.gc_all(keep_last_n=keep_last_n)


_DASHBOARD_COLUMNS = [
    ("derived_id", pl.String),
    ("version", pl.Int64),
    ("role", pl.String),
    ("profile", pl.String),
    ("version_status", pl.String),
    ("is_online", pl.Boolean),
    ("is_primary", pl.Boolean),
    ("active_version", pl.Int64),
    ("latest_run_id", pl.String),
    ("latest_run_status", pl.String),
    ("total_rows", pl.Int64),
    ("watermark", pl.String),
]


def _dashboard_schema() -> dict[str, type[pl.DataType]]:
    """Build a schema dict for the dashboard DataFrame."""
    return dict(_DASHBOARD_COLUMNS)


def _empty_dashboard() -> pl.DataFrame:
    """Create an empty dashboard frame with the canonical schema."""
    return pl.DataFrame(
        {
            name: pl.Series(name=name, values=[], dtype=dtype)
            for name, dtype in _DASHBOARD_COLUMNS
        }
    )
