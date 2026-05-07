"""Product-neutral data catalog contract types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = [
    "DataAssetRef",
    "DataCatalogEntry",
    "DataCatalogReader",
    "DataCatalogWriter",
    "DataSchemaFingerprint",
]


@dataclass(frozen=True)
class DataAssetRef:
    """Stable reference to a logical data asset."""

    dataset_id: str
    namespace: str
    partition_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataSchemaFingerprint:
    """Content-independent schema fingerprint and optional observation metadata."""

    schema_hash: str
    row_count: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class DataCatalogEntry:
    """Catalog metadata with an implementation-neutral URI for the asset payload."""

    asset: DataAssetRef
    storage_uri: str
    schema: DataSchemaFingerprint
    source: str
    freshness_at: datetime


@runtime_checkable
class DataCatalogReader(Protocol):
    """Read-only access to catalog entries."""

    def get_asset(self, asset: DataAssetRef) -> DataCatalogEntry | None:
        """Return a catalog entry for an asset if it is registered."""
        ...

    def list_assets(
        self,
        namespace: str | None = None,
    ) -> tuple[DataCatalogEntry, ...]:
        """Return catalog entries, optionally limited to one namespace."""
        ...


@runtime_checkable
class DataCatalogWriter(Protocol):
    """Write access to catalog entries."""

    def upsert_asset(self, entry: DataCatalogEntry) -> None:
        """Insert or replace a catalog entry."""
        ...
