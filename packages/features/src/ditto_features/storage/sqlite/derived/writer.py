"""SQLite-backed writer for unified derived runtime metadata."""

import orjson
from ditto_platform.foundation import SQLiteClient

from ditto_features.errors import FeatureStorageError
from ditto_features.models.derived import (
    DerivedCheckpointRecord,
    DerivedCheckpointStatus,
    DerivedDependencyRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)

__all__ = ["SQLiteDerivedCatalogWriter"]

_VALID_VERSION_STATUSES: frozenset[str] = frozenset(
    {
        "draft",
        "materialized",
        "published",
        "deprecated",
        "archived",
    }
)
_VALID_RUN_STATUSES: frozenset[str] = frozenset(
    {
        "RUNNING",
        "SUCCESS",
        "FAILED",
    }
)
_VALID_CHECKPOINT_STATUSES: frozenset[str] = frozenset(
    status.value for status in DerivedCheckpointStatus
)


def _invalid_status_error(
    message: str,
    *,
    table: str,
    status: str,
    allowed_statuses: frozenset[str],
) -> FeatureStorageError:
    """Build a FeatureStorageError for derived catalog status validation."""
    return FeatureStorageError(
        message,
        table=table,
        status=status,
        allowed_statuses=tuple(sorted(allowed_statuses)),
    )


class SQLiteDerivedCatalogWriter:
    """
    Persist derived catalog and runtime metadata into SQLite.

    Each ``write_*`` method executes SQL and immediately commits.
    For batch operations that require a single transaction, use the
    ``execute_*`` methods (SQL without commit) together with
    ``commit()`` / ``rollback()``.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    # --- transaction control (UoW) ---

    def commit(self) -> None:
        """Commit the current transaction."""
        self._sqlite_client.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._sqlite_client.rollback()

    # --- execute methods (no commit) ---

    def execute_spec(self, record: DerivedSpecRecord) -> None:
        """Execute spec INSERT without committing."""
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

    def execute_version(self, record: DerivedVersionRecord) -> None:
        """Execute version INSERT without committing."""
        if record.status not in _VALID_VERSION_STATUSES:
            msg = (
                f"invalid version status: {record.status!r}, "
                f"expected one of {sorted(_VALID_VERSION_STATUSES)}"
            )
            raise _invalid_status_error(
                msg,
                table="derived_version",
                status=record.status,
                allowed_statuses=_VALID_VERSION_STATUSES,
            )
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

    def execute_run(self, record: DerivedRunRecord) -> None:
        """Execute run INSERT without committing."""
        if record.status not in _VALID_RUN_STATUSES:
            msg = (
                f"invalid run status: {record.status!r}, "
                f"expected one of {sorted(_VALID_RUN_STATUSES)}"
            )
            raise _invalid_status_error(
                msg,
                table="derived_run",
                status=record.status,
                allowed_statuses=_VALID_RUN_STATUSES,
            )
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

    def execute_state(self, record: DerivedStateRecord) -> None:
        """Execute state INSERT without committing."""
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

    def execute_partitions(self, records: tuple[DerivedPartitionRecord, ...]) -> None:
        """Execute partition INSERTs without committing."""
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

    def execute_checkpoints(self, records: tuple[DerivedCheckpointRecord, ...]) -> None:
        """Execute checkpoint INSERTs without committing."""
        if not records:
            return
        for record in records:
            if record.status not in _VALID_CHECKPOINT_STATUSES:
                msg = (
                    f"invalid checkpoint status: {record.status!r}, "
                    f"expected one of {sorted(_VALID_CHECKPOINT_STATUSES)}"
                )
                raise _invalid_status_error(
                    msg,
                    table="derived_checkpoint",
                    status=record.status,
                    allowed_statuses=_VALID_CHECKPOINT_STATUSES,
                )
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

    def execute_dependencies(
        self, records: tuple[DerivedDependencyRecord, ...]
    ) -> None:
        """Execute dependency INSERTs without committing."""
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

    # --- write methods (execute + commit) ---

    def write_spec(self, record: DerivedSpecRecord) -> None:
        """Persist one derived spec row."""
        self.execute_spec(record)
        self.commit()

    def write_version(self, record: DerivedVersionRecord) -> None:
        """Persist one derived version row."""
        self.execute_version(record)
        self.commit()

    def write_run(self, record: DerivedRunRecord) -> None:
        """Persist one materialization run row."""
        self.execute_run(record)
        self.commit()

    def write_state(self, record: DerivedStateRecord) -> None:
        """Persist the latest durable state row."""
        self.execute_state(record)
        self.commit()

    def write_partitions(self, records: tuple[DerivedPartitionRecord, ...]) -> None:
        """Persist partition rows for one run."""
        self.execute_partitions(records)
        self.commit()

    def write_checkpoints(self, records: tuple[DerivedCheckpointRecord, ...]) -> None:
        """Persist checkpoint rows for durable partitions."""
        self.execute_checkpoints(records)
        self.commit()

    def write_dependencies(self, records: tuple[DerivedDependencyRecord, ...]) -> None:
        """Persist dependency rows."""
        self.execute_dependencies(records)
        self.commit()

    def publish_version(
        self,
        derived_id: str,
        version: int,
        updated_at: str,
    ) -> None:
        """
        Advance one version to published/primary and demote other primaries.

        Both UPDATEs run in a single transaction so the primary pointer never
        shows two owners (or none) to a concurrent reader.
        """
        self._sqlite_client.execute(
            """
            UPDATE derived_version
            SET status = 'published', is_online = 1, is_primary = 1, updated_at = ?
            WHERE derived_id = ? AND version = ?
            """,
            (updated_at, derived_id, version),
        )
        self._sqlite_client.execute(
            """
            UPDATE derived_version
            SET is_primary = 0, updated_at = ?
            WHERE derived_id = ? AND version <> ? AND is_primary = 1
            """,
            (updated_at, derived_id, version),
        )
        self.commit()

    # --- delete methods ---

    def execute_delete_version_records(
        self,
        derived_id: str,
        version: int,
    ) -> int:
        """
        Delete all records for one derived version without committing.

        Removes rows from derived_run, derived_partition,
        derived_checkpoint, derived_spec, and derived_version.

        Does NOT touch derived_state or derived_dependency (managed
        separately).

        Returns the number of records removed.
        """
        total = 0
        delete_order = [
            "derived_partition",
            "derived_checkpoint",
            "derived_run",
            "derived_spec",
            "derived_version",
        ]
        for table in delete_order:
            cursor = self._sqlite_client.execute(
                f"DELETE FROM {table} WHERE derived_id = ? AND version = ?",  # noqa: S608 - table 来自受控枚举，参数使用占位符
                (derived_id, version),
            )
            total += cursor.rowcount
        return total

    def delete_version_records(self, derived_id: str, version: int) -> int:
        """Delete all records for one derived version and commit."""
        total = self.execute_delete_version_records(derived_id, version)
        self.commit()
        return total
