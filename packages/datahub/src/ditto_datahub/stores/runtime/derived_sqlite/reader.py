"""SQLite-backed reader for unified derived runtime metadata."""

from typing import Any

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

__all__ = ["SQLiteDerivedCatalogReader"]


class SQLiteDerivedCatalogReader:
    """Read derived catalog and runtime metadata from SQLite."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def has_any_records(self) -> bool:
        """Whether any derived runtime metadata rows exist."""
        return bool(
            self._sqlite_client.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM derived_spec
                    UNION ALL
                    SELECT 1 FROM derived_version
                    UNION ALL
                    SELECT 1 FROM derived_run
                    UNION ALL
                    SELECT 1 FROM derived_partition
                    UNION ALL
                    SELECT 1 FROM derived_state
                )
                """
            )
        )

    def read_spec(self, derived_id: str, version: int) -> DerivedSpecRecord | None:
        """Read one derived spec row."""
        row = self._sqlite_client.fetchone(
            """
            SELECT derived_id, version, role, materialization_profile,
                   spec_hash, spec_json, created_at
            FROM derived_spec
            WHERE derived_id = ? AND version = ?
            """,
            (derived_id, version),
        )
        if row is None:
            return None
        return _to_spec_record(row)

    def read_version(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedVersionRecord | None:
        """Read one derived version row."""
        row = self._sqlite_client.fetchone(
            """
            SELECT derived_id, version, status, engine_version,
                   is_online, is_primary, created_at, updated_at
            FROM derived_version
            WHERE derived_id = ? AND version = ?
            """,
            (derived_id, version),
        )
        if row is None:
            return None
        return _to_version_record(row)

    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]:
        """List all version rows for one derived id."""
        rows = self._sqlite_client.fetchall(
            """
            SELECT derived_id, version, status, engine_version,
                   is_online, is_primary, created_at, updated_at
            FROM derived_version
            WHERE derived_id = ?
            ORDER BY version ASC
            """,
            (derived_id,),
        )
        return tuple(_to_version_record(row) for row in rows)

    def read_run(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> DerivedRunRecord | None:
        """Read one materialization run row."""
        row = self._sqlite_client.fetchone(
            """
            SELECT run_id, derived_id, version, mode, trigger,
                   request_start, request_end, compute_start, compute_end,
                   source_snapshot_id, status, rows_written,
                   partitions_written, error_message,
                   created_at, started_at, finished_at
            FROM derived_run
            WHERE derived_id = ? AND version = ? AND run_id = ?
            """,
            (derived_id, version, run_id),
        )
        if row is None:
            return None
        return _to_run_record(row)

    def get_latest_run(self, derived_id: str, version: int) -> DerivedRunRecord | None:
        """Read the latest run row for one derived version."""
        row = self._sqlite_client.fetchone(
            """
            SELECT run_id, derived_id, version, mode, trigger,
                   request_start, request_end, compute_start, compute_end,
                   source_snapshot_id, status, rows_written,
                   partitions_written, error_message,
                   created_at, started_at, finished_at
            FROM derived_run
            WHERE derived_id = ? AND version = ?
            ORDER BY created_at DESC, run_id DESC
            LIMIT 1
            """,
            (derived_id, version),
        )
        if row is None:
            return None
        return _to_run_record(row)

    def read_state(self, derived_id: str) -> DerivedStateRecord | None:
        """Read the latest durable state row for one derived id."""
        row = self._sqlite_client.fetchone(
            """
            SELECT derived_id, active_version, coverage_start, coverage_end, watermark,
                   latest_run_id, latest_run_status, total_rows, updated_at
            FROM derived_state
            WHERE derived_id = ?
            """,
            (derived_id,),
        )
        if row is None:
            return None
        return DerivedStateRecord(
            derived_id=row["derived_id"],
            active_version=row["active_version"],
            coverage_start=row["coverage_start"],
            coverage_end=row["coverage_end"],
            watermark=row["watermark"],
            latest_run_id=row["latest_run_id"],
            latest_run_status=row["latest_run_status"],
            total_rows=row["total_rows"],
            updated_at=row["updated_at"],
        )

    def list_partitions(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> list[DerivedPartitionRecord]:
        """List partition rows written by one run."""
        rows = self._sqlite_client.fetchall(
            """
            SELECT run_id, derived_id, version, partition_key,
                   partition_path, row_count, checksum, written_at
            FROM derived_partition
            WHERE derived_id = ? AND version = ? AND run_id = ?
            ORDER BY partition_key ASC
            """,
            (derived_id, version, run_id),
        )
        return [_to_partition_record(row) for row in rows]

    def list_checkpoints(
        self,
        derived_id: str,
        version: int,
    ) -> tuple[DerivedCheckpointRecord, ...]:
        """List checkpoint rows for one derived version."""
        rows = self._sqlite_client.fetchall(
            """
            SELECT derived_id, version, partition_key, status, rows_written, checksum,
                   error_message, started_at, completed_at
            FROM derived_checkpoint
            WHERE derived_id = ? AND version = ?
            ORDER BY partition_key ASC
            """,
            (derived_id, version),
        )
        return tuple(
            DerivedCheckpointRecord(
                derived_id=row["derived_id"],
                version=row["version"],
                partition_key=row["partition_key"],
                status=row["status"],
                rows_written=row["rows_written"],
                checksum=row["checksum"],
                error_message=row["error_message"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
            )
            for row in rows
        )

    def list_dependencies_by_ref(
        self,
        dependency_ref: str,
    ) -> tuple[DerivedDependencyRecord, ...]:
        """List downstream dependency rows for one upstream reference."""
        rows = self._sqlite_client.fetchall(
            """
            SELECT derived_id, version, dependency_kind, dependency_ref, created_at
            FROM derived_dependency
            WHERE dependency_ref = ?
            ORDER BY derived_id ASC, version ASC
            """,
            (dependency_ref,),
        )
        return tuple(
            DerivedDependencyRecord(
                derived_id=row["derived_id"],
                version=row["version"],
                dependency_kind=row["dependency_kind"],
                dependency_ref=row["dependency_ref"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def list_pending_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List pending invalidation rows in processing order."""
        rows = self._sqlite_client.fetchall(
            """
            SELECT invalidation_id, derived_id, version,
                   source_domain, source_dataset, change_date,
                   affected_start, affected_end,
                   source_snapshot_id, root_dependency_ref,
                   status, created_at, processed_at, depth,
                   retry_count, error_message, dead_letter_at, role
            FROM derived_invalidation
            WHERE status = 'pending'
            ORDER BY created_at ASC, invalidation_id ASC
            """,
        )
        return tuple(_to_invalidation_record(row) for row in rows)

    def list_stale_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List stale invalidation rows ordered by role priority then depth."""
        rows = self._sqlite_client.fetchall(
            """
            SELECT invalidation_id, derived_id, version,
                   source_domain, source_dataset, change_date,
                   affected_start, affected_end,
                   source_snapshot_id, root_dependency_ref,
                   status, created_at, processed_at, depth,
                   retry_count, error_message, dead_letter_at, role
            FROM derived_invalidation
            WHERE status = 'stale'
            ORDER BY
                CASE role
                    WHEN 'signal' THEN 0 WHEN 'factor' THEN 1
                    WHEN 'label' THEN 2 WHEN 'feature' THEN 3 ELSE 4
                END ASC,
                depth ASC, created_at ASC, invalidation_id ASC
            """,
        )
        return tuple(_to_invalidation_record(row) for row in rows)

    def list_dead_letter_invalidations(self) -> tuple[DerivedInvalidationRecord, ...]:
        """List dead-letter invalidation rows ordered by dead_letter_at."""
        rows = self._sqlite_client.fetchall(
            """
            SELECT invalidation_id, derived_id, version,
                   source_domain, source_dataset, change_date,
                   affected_start, affected_end,
                   source_snapshot_id, root_dependency_ref,
                   status, created_at, processed_at, depth,
                   retry_count, error_message, dead_letter_at, role
            FROM derived_invalidation
            WHERE status = 'dead_letter'
            ORDER BY dead_letter_at ASC
            """,
        )
        return tuple(_to_invalidation_record(row) for row in rows)

    def list_specs(
        self,
        derived_ids: tuple[str, ...] | None = None,
        durable_only: bool = False,
    ) -> tuple[DerivedSpecRecord, ...]:
        """List active spec rows, with optional durable and id filtering."""
        rows = self._sqlite_client.fetchall(_build_list_specs_sql(durable_only))
        records = tuple(_to_spec_record(row) for row in rows)
        if derived_ids is None:
            return records
        allowed_ids = set(derived_ids)
        return tuple(record for record in records if record.derived_id in allowed_ids)


def _build_list_specs_sql(durable_only: bool) -> str:
    if durable_only:
        return """
        SELECT s.derived_id, s.version, s.role, s.materialization_profile,
               s.spec_hash, s.spec_json, s.created_at
        FROM derived_spec AS s
        INNER JOIN derived_version AS v
            ON s.derived_id = v.derived_id AND s.version = v.version
        WHERE v.status IN ('published')
          AND s.materialization_profile IN ('SERIES', 'STATE', 'OFFLINE')
        ORDER BY s.derived_id ASC, s.version ASC
        """
    return """
    SELECT s.derived_id, s.version, s.role, s.materialization_profile,
           s.spec_hash, s.spec_json, s.created_at
    FROM derived_spec AS s
    INNER JOIN derived_version AS v
        ON s.derived_id = v.derived_id AND s.version = v.version
    WHERE v.status IN ('published')
    ORDER BY s.derived_id ASC, s.version ASC
    """


def _to_spec_record(row: dict[str, Any]) -> DerivedSpecRecord:
    return DerivedSpecRecord(
        derived_id=row["derived_id"],
        version=row["version"],
        role=row["role"],
        materialization_profile=row["materialization_profile"],
        spec_hash=row["spec_hash"],
        spec_json=orjson.loads(row["spec_json"]),
        created_at=row["created_at"],
    )


def _to_version_record(row: dict[str, Any]) -> DerivedVersionRecord:
    return DerivedVersionRecord(
        derived_id=row["derived_id"],
        version=row["version"],
        status=row["status"],
        engine_version=row["engine_version"],
        is_online=bool(row["is_online"]),
        is_primary=bool(row["is_primary"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_run_record(row: dict[str, Any]) -> DerivedRunRecord:
    return DerivedRunRecord(
        run_id=row["run_id"],
        derived_id=row["derived_id"],
        version=row["version"],
        mode=row["mode"],
        trigger=row["trigger"],
        request_start=row["request_start"],
        request_end=row["request_end"],
        compute_start=row["compute_start"],
        compute_end=row["compute_end"],
        source_snapshot_id=row["source_snapshot_id"],
        status=row["status"],
        rows_written=row["rows_written"],
        partitions_written=tuple(orjson.loads(row["partitions_written"])),
        error_message=row["error_message"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _to_partition_record(row: dict[str, Any]) -> DerivedPartitionRecord:
    return DerivedPartitionRecord(
        run_id=row["run_id"],
        derived_id=row["derived_id"],
        version=row["version"],
        partition_key=row["partition_key"],
        partition_path=row["partition_path"],
        row_count=row["row_count"],
        checksum=row["checksum"],
        written_at=row["written_at"],
    )


def _to_invalidation_record(row: dict[str, Any]) -> DerivedInvalidationRecord:
    return DerivedInvalidationRecord(
        invalidation_id=row["invalidation_id"],
        derived_id=row["derived_id"],
        version=row["version"],
        source_domain=row["source_domain"],
        source_dataset=row["source_dataset"],
        change_date=row["change_date"],
        affected_start=row["affected_start"],
        affected_end=row["affected_end"],
        source_snapshot_id=row["source_snapshot_id"],
        root_dependency_ref=row["root_dependency_ref"],
        status=row["status"],
        created_at=row["created_at"],
        processed_at=row["processed_at"],
        depth=row["depth"],
        retry_count=row["retry_count"],
        error_message=row["error_message"],
        dead_letter_at=row["dead_letter_at"],
        role=row["role"],
    )
