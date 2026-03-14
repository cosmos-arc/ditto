"""SQLite-backed writer for unified derived runtime metadata."""

import orjson
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
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = ["SQLiteDerivedCatalogWriter"]


class SQLiteDerivedCatalogWriter:
    """Persist derived catalog and runtime metadata into SQLite."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def write_spec(self, record: DerivedSpecRecord) -> None:
        """Persist one derived spec row."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO derived_spec (
                derived_id, version, role, materialization_profile,
                spec_hash, spec_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.derived_id,
                record.version,
                record.role,
                record.materialization_profile,
                record.spec_hash,
                orjson.dumps(record.spec_json).decode(),
                record.created_at,
            ),
        )
        self._sqlite_client.commit()

    def write_version(self, record: DerivedVersionRecord) -> None:
        """Persist one derived version row."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO derived_version (
                derived_id, version, status, engine_version,
                is_online, is_primary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.derived_id,
                record.version,
                record.status,
                record.engine_version,
                int(record.is_online),
                int(record.is_primary),
                record.created_at,
                record.updated_at,
            ),
        )
        self._sqlite_client.commit()

    def write_run(self, record: DerivedRunRecord) -> None:
        """Persist one materialization run row."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO derived_run (
                run_id, derived_id, version, mode, trigger,
                request_start, request_end, compute_start, compute_end,
                source_snapshot_id, status, rows_written,
                partitions_written, error_message,
                created_at, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.derived_id,
                record.version,
                record.mode,
                record.trigger,
                record.request_start,
                record.request_end,
                record.compute_start,
                record.compute_end,
                record.source_snapshot_id,
                record.status,
                record.rows_written,
                orjson.dumps(record.partitions_written).decode(),
                record.error_message,
                record.created_at,
                record.started_at,
                record.finished_at,
            ),
        )
        self._sqlite_client.commit()

    def write_state(self, record: DerivedStateRecord) -> None:
        """Persist the latest durable state row."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO derived_state (
                derived_id, active_version, coverage_start, coverage_end, watermark,
                latest_run_id, latest_run_status, total_rows, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.derived_id,
                record.active_version,
                record.coverage_start,
                record.coverage_end,
                record.watermark,
                record.latest_run_id,
                record.latest_run_status,
                record.total_rows,
                record.updated_at,
            ),
        )
        self._sqlite_client.commit()

    def write_partitions(self, records: tuple[DerivedPartitionRecord, ...]) -> None:
        """Persist partition rows for one run."""
        if not records:
            return
        self._sqlite_client.executemany(
            """
            INSERT OR REPLACE INTO derived_partition (
                run_id, derived_id, version, partition_key,
                partition_path, row_count, checksum, written_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.run_id,
                    record.derived_id,
                    record.version,
                    record.partition_key,
                    record.partition_path,
                    record.row_count,
                    record.checksum,
                    record.written_at,
                )
                for record in records
            ],
        )
        self._sqlite_client.commit()

    def write_checkpoints(self, records: tuple[DerivedCheckpointRecord, ...]) -> None:
        """Persist checkpoint rows for durable partitions."""
        if not records:
            return
        self._sqlite_client.executemany(
            """
            INSERT OR REPLACE INTO derived_checkpoint (
                derived_id, version, partition_key, status, rows_written, checksum,
                error_message, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.derived_id,
                    record.version,
                    record.partition_key,
                    record.status,
                    record.rows_written,
                    record.checksum,
                    record.error_message,
                    record.started_at,
                    record.completed_at,
                )
                for record in records
            ],
        )
        self._sqlite_client.commit()

    def write_dependencies(self, records: tuple[DerivedDependencyRecord, ...]) -> None:
        """Persist dependency rows."""
        if not records:
            return
        self._sqlite_client.executemany(
            """
            INSERT OR REPLACE INTO derived_dependency (
                derived_id, version, dependency_kind, dependency_ref, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    record.derived_id,
                    record.version,
                    record.dependency_kind,
                    record.dependency_ref,
                    record.created_at,
                )
                for record in records
            ],
        )
        self._sqlite_client.commit()

    def write_invalidations(
        self,
        records: tuple[DerivedInvalidationRecord, ...],
    ) -> None:
        """Persist invalidation rows."""
        if not records:
            return
        self._sqlite_client.executemany(
            """
            INSERT OR REPLACE INTO derived_invalidation (
                invalidation_id, derived_id, version,
                source_domain, source_dataset, change_date,
                affected_start, affected_end,
                source_snapshot_id, root_dependency_ref,
                status, created_at, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.invalidation_id,
                    record.derived_id,
                    record.version,
                    record.source_domain,
                    record.source_dataset,
                    record.change_date,
                    record.affected_start,
                    record.affected_end,
                    record.source_snapshot_id,
                    record.root_dependency_ref,
                    record.status,
                    record.created_at,
                    record.processed_at,
                )
                for record in records
            ],
        )
        self._sqlite_client.commit()

    def mark_invalidation_processed(
        self,
        invalidation_id: str,
        processed_at: str,
    ) -> None:
        """Mark one invalidation row as processed."""
        self._sqlite_client.execute(
            """
            UPDATE derived_invalidation
            SET status = 'processed', processed_at = ?
            WHERE invalidation_id = ?
            """,
            (processed_at, invalidation_id),
        )
        self._sqlite_client.commit()
