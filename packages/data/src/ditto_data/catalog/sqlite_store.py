"""SQLite-backed DataCatalog implementation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.storage_policy import validate_catalog_storage_location

__all__ = ["SQLiteDataCatalog"]


def _partition_keys_json(partition_keys: tuple[str, ...]) -> str:
    return json.dumps(list(partition_keys), ensure_ascii=True, separators=(",", ":"))


def _partition_keys_from_json(value: str) -> tuple[str, ...]:
    parsed: object = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("catalog asset partition keys must be a JSON string list")
    values = cast(list[object], parsed)
    partition_keys: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("catalog asset partition keys must be a JSON string list")
        partition_keys.append(item)
    return tuple(partition_keys)


def _schema_columns_json(columns: tuple[str, ...]) -> str:
    return json.dumps(list(columns), ensure_ascii=True, separators=(",", ":"))


def _schema_columns_from_json(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    parsed: object = json.loads(str(value))
    if not isinstance(parsed, list):
        raise ValueError("catalog schema columns must be a JSON string list")
    values = cast(list[object], parsed)
    columns: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("catalog schema columns must be a JSON string list")
        columns.append(item)
    return tuple(columns)


def _asset_params(asset: DataAssetRef) -> tuple[str, str, str]:
    return (
        asset.namespace,
        asset.dataset_id,
        _partition_keys_json(asset.partition_keys),
    )


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError("catalog schema row count must be an integer or string")


class SQLiteDataCatalog:
    """Durable catalog store for logical data asset metadata."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS data_catalog_entries (
                asset_namespace TEXT NOT NULL,
                asset_dataset_id TEXT NOT NULL,
                asset_partition_keys TEXT NOT NULL,
                storage_uri TEXT NOT NULL,
                schema_hash TEXT NOT NULL,
                schema_version TEXT,
                schema_columns TEXT,
                schema_row_count INTEGER,
                schema_created_at TEXT,
                source TEXT NOT NULL,
                freshness_at TEXT NOT NULL,
                source_snapshot_id TEXT,
                PRIMARY KEY (
                    asset_namespace,
                    asset_dataset_id,
                    asset_partition_keys
                )
            )
            """,
        )
        self._ensure_optional_schema_metadata_columns()
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_data_catalog_entries_namespace
            ON data_catalog_entries(asset_namespace)
            """,
        )
        self._client.commit()

    def _ensure_optional_schema_metadata_columns(self) -> None:
        """Backfill catalog schema metadata columns for existing SQLite files."""
        rows = self._client.fetchall("PRAGMA table_info(data_catalog_entries)")
        existing = {str(row["name"]) for row in rows}
        if "schema_version" not in existing:
            self._client.execute(
                "ALTER TABLE data_catalog_entries ADD COLUMN schema_version TEXT"
            )
        if "schema_columns" not in existing:
            self._client.execute(
                "ALTER TABLE data_catalog_entries ADD COLUMN schema_columns TEXT"
            )
        if "source_snapshot_id" not in existing:
            self._client.execute(
                "ALTER TABLE data_catalog_entries ADD COLUMN source_snapshot_id TEXT"
            )

    def upsert_asset(self, entry: DataCatalogEntry) -> None:
        """Insert or replace a catalog entry."""
        validate_catalog_storage_location(entry)
        try:
            self._client.execute(
                """
                INSERT INTO data_catalog_entries (
                    asset_namespace,
                    asset_dataset_id,
                    asset_partition_keys,
                    storage_uri,
                    schema_hash,
                    schema_version,
                    schema_columns,
                    schema_row_count,
                    schema_created_at,
                    source,
                    freshness_at,
                    source_snapshot_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    asset_namespace,
                    asset_dataset_id,
                    asset_partition_keys
                )
                DO UPDATE SET
                    storage_uri = excluded.storage_uri,
                    schema_hash = excluded.schema_hash,
                    schema_version = excluded.schema_version,
                    schema_columns = excluded.schema_columns,
                    schema_row_count = excluded.schema_row_count,
                    schema_created_at = excluded.schema_created_at,
                    source = excluded.source,
                    freshness_at = excluded.freshness_at,
                    source_snapshot_id = excluded.source_snapshot_id
                """,
                [
                    entry.asset.namespace,
                    entry.asset.dataset_id,
                    _partition_keys_json(entry.asset.partition_keys),
                    entry.storage_uri,
                    entry.schema.schema_hash,
                    entry.schema.schema_version,
                    _schema_columns_json(entry.schema.columns),
                    entry.schema.row_count,
                    entry.schema.created_at.isoformat()
                    if entry.schema.created_at is not None
                    else None,
                    entry.source,
                    entry.freshness_at.isoformat(),
                    entry.source_snapshot_id,
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def get_asset(self, asset: DataAssetRef) -> DataCatalogEntry | None:
        """Return a catalog entry if registered, else None."""
        row = self._client.fetchone(
            """
            SELECT
                asset_namespace,
                asset_dataset_id,
                asset_partition_keys,
                storage_uri,
                schema_hash,
                schema_version,
                schema_columns,
                schema_row_count,
                schema_created_at,
                source,
                freshness_at,
                source_snapshot_id
            FROM data_catalog_entries
            WHERE asset_namespace = ?
              AND asset_dataset_id = ?
              AND asset_partition_keys = ?
            """,
            _asset_params(asset),
        )
        if row is None:
            return None
        return _entry_from_row(row)

    def list_assets(
        self,
        namespace: str | None = None,
    ) -> tuple[DataCatalogEntry, ...]:
        """Return entries, optionally filtered by namespace."""
        if namespace is None:
            rows = self._client.fetchall(
                """
                SELECT
                    asset_namespace,
                    asset_dataset_id,
                    asset_partition_keys,
                    storage_uri,
                    schema_hash,
                    schema_version,
                    schema_columns,
                    schema_row_count,
                    schema_created_at,
                    source,
                    freshness_at,
                    source_snapshot_id
                FROM data_catalog_entries
                ORDER BY asset_namespace, asset_dataset_id, asset_partition_keys
                """,
            )
        else:
            rows = self._client.fetchall(
                """
                SELECT
                    asset_namespace,
                    asset_dataset_id,
                    asset_partition_keys,
                    storage_uri,
                    schema_hash,
                    schema_version,
                    schema_columns,
                    schema_row_count,
                    schema_created_at,
                    source,
                    freshness_at,
                    source_snapshot_id
                FROM data_catalog_entries
                WHERE asset_namespace = ?
                ORDER BY asset_namespace, asset_dataset_id, asset_partition_keys
                """,
                [namespace],
            )
        return tuple(_entry_from_row(row) for row in rows)


def _entry_from_row(row: dict[str, Any]) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=str(row["asset_dataset_id"]),
            namespace=str(row["asset_namespace"]),
            partition_keys=_partition_keys_from_json(str(row["asset_partition_keys"])),
        ),
        storage_uri=str(row["storage_uri"]),
        schema=DataSchemaFingerprint(
            schema_hash=str(row["schema_hash"]),
            row_count=_optional_int(row["schema_row_count"]),
            created_at=_optional_datetime(row["schema_created_at"]),
            schema_version=str(row["schema_version"])
            if row["schema_version"] is not None
            else None,
            columns=_schema_columns_from_json(row["schema_columns"]),
        ),
        source=str(row["source"]),
        freshness_at=datetime.fromisoformat(str(row["freshness_at"])),
        source_snapshot_id=(
            str(row["source_snapshot_id"])
            if row.get("source_snapshot_id") is not None
            else None
        ),
    )
