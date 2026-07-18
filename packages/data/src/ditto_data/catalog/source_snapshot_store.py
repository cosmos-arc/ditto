"""SQLite persistence for provider-specific immutable snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import orjson
from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot
from ditto_data.storage.base.sqlite_helpers import (
    partition_keys_from_json,
    partition_keys_json,
)

__all__ = ["SQLiteProviderSnapshotStore"]


def _metadata_json(metadata: tuple[tuple[str, str], ...]) -> str:
    return orjson.dumps(dict(metadata)).decode()


def _metadata_from_json(value: object) -> tuple[tuple[str, str], ...]:
    parsed: object = orjson.loads(str(value))
    if not isinstance(parsed, dict):
        raise ValueError("provider snapshot response metadata must be an object")
    typed = cast(dict[object, object], parsed)
    if any(
        not isinstance(key, str) or not isinstance(item, str)
        for key, item in typed.items()
    ):
        raise ValueError(
            "provider snapshot response metadata must contain string pairs"
        )
    return tuple(sorted((str(key), str(item)) for key, item in typed.items()))


class SQLiteProviderSnapshotStore:
    """Append-only provider snapshot store."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                source TEXT NOT NULL,
                request_start TEXT NOT NULL,
                request_end TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                checksum TEXT NOT NULL,
                canonical_namespace TEXT NOT NULL,
                canonical_dataset_id TEXT NOT NULL,
                canonical_partition_keys TEXT NOT NULL,
                request_parameters_hash TEXT NOT NULL,
                response_metadata TEXT NOT NULL,
                license_record_id TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                payload_uri TEXT,
                payload_retained INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provider_snapshots_canonical
            ON provider_snapshots(
                canonical_namespace,
                canonical_dataset_id,
                canonical_partition_keys,
                source
            )
            """
        )
        self._client.commit()

    def append_snapshot(self, snapshot: ProviderSnapshot) -> None:
        """Append a snapshot, treating an exact duplicate as idempotent."""
        existing = self.get_snapshot(snapshot.snapshot_id)
        if existing is not None:
            if existing == snapshot:
                return
            raise ValueError(
                f"immutable provider snapshot conflict: {snapshot.snapshot_id}"
            )
        if snapshot.snapshot_id != snapshot.expected_snapshot_id():
            raise ValueError(
                "provider snapshot identity does not match required fields"
            )
        try:
            self._client.execute(
                """
                INSERT INTO provider_snapshots (
                    snapshot_id, dataset_id, source, request_start, request_end,
                    schema_version, checksum, canonical_namespace,
                    canonical_dataset_id, canonical_partition_keys,
                    request_parameters_hash, response_metadata, license_record_id,
                    row_count, payload_uri, payload_retained, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    snapshot.snapshot_id,
                    snapshot.dataset_id,
                    snapshot.source,
                    snapshot.request_start,
                    snapshot.request_end,
                    snapshot.schema_version,
                    snapshot.checksum,
                    snapshot.canonical_asset.namespace,
                    snapshot.canonical_asset.dataset_id,
                    partition_keys_json(snapshot.canonical_asset.partition_keys),
                    snapshot.request_parameters_hash,
                    _metadata_json(snapshot.response_metadata),
                    snapshot.license_record_id,
                    snapshot.row_count,
                    snapshot.payload_uri,
                    int(snapshot.payload_retained),
                    snapshot.created_at.isoformat(),
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        """Return one immutable provider snapshot by ID."""
        row = self._client.fetchone(
            "SELECT * FROM provider_snapshots WHERE snapshot_id = ?",
            [snapshot_id],
        )
        return None if row is None else _snapshot_from_row(row)

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        """List snapshots with optional product/provider/canonical filters."""
        canonical_namespace = (
            canonical_asset.namespace if canonical_asset is not None else None
        )
        canonical_dataset_id = (
            canonical_asset.dataset_id if canonical_asset is not None else None
        )
        canonical_partition_keys = (
            partition_keys_json(canonical_asset.partition_keys)
            if canonical_asset is not None
            else None
        )
        rows = self._client.fetchall(
            """
            SELECT * FROM provider_snapshots
            WHERE (? IS NULL OR dataset_id = ?)
              AND (? IS NULL OR source = ?)
              AND (
                    ? IS NULL
                    OR (
                        canonical_namespace = ?
                        AND canonical_dataset_id = ?
                        AND canonical_partition_keys = ?
                    )
              )
            ORDER BY source, snapshot_id
            """,
            [
                dataset_id,
                dataset_id,
                source,
                source,
                canonical_namespace,
                canonical_namespace,
                canonical_dataset_id,
                canonical_partition_keys,
            ],
        )
        return tuple(_snapshot_from_row(row) for row in rows)


def _snapshot_from_row(row: dict[str, Any]) -> ProviderSnapshot:
    return ProviderSnapshot(
        snapshot_id=str(row["snapshot_id"]),
        dataset_id=str(row["dataset_id"]),
        source=str(row["source"]),
        request_start=str(row["request_start"]),
        request_end=str(row["request_end"]),
        schema_version=str(row["schema_version"]),
        checksum=str(row["checksum"]),
        canonical_asset=DataAssetRef(
            dataset_id=str(row["canonical_dataset_id"]),
            namespace=str(row["canonical_namespace"]),
            partition_keys=partition_keys_from_json(
                str(row["canonical_partition_keys"])
            ),
        ),
        request_parameters_hash=str(row["request_parameters_hash"]),
        response_metadata=_metadata_from_json(row["response_metadata"]),
        license_record_id=str(row["license_record_id"]),
        row_count=int(row["row_count"]),
        payload_uri=(
            str(row["payload_uri"]) if row["payload_uri"] is not None else None
        ),
        payload_retained=bool(row["payload_retained"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )
