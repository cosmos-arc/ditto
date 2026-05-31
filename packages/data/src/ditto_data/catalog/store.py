"""In-memory DataCatalog implementation."""

from __future__ import annotations

from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
)

__all__ = ["InMemoryDataCatalog"]


class InMemoryDataCatalog:
    """In-memory DataCatalog for testing and development."""

    def __init__(self) -> None:
        """
        初始化空的内存数据目录。

        所有 catalog entry 存储在进程内字典中，适用于测试和开发环境。
        """
        self._entries: dict[DataAssetRef, DataCatalogEntry] = {}

    def upsert_asset(self, entry: DataCatalogEntry) -> None:
        """Insert or replace a catalog entry."""
        self._entries[entry.asset] = entry

    def get_asset(self, asset: DataAssetRef) -> DataCatalogEntry | None:
        """Return a catalog entry if registered, else None."""
        return self._entries.get(asset)

    def list_assets(
        self,
        namespace: str | None = None,
    ) -> tuple[DataCatalogEntry, ...]:
        """Return entries, optionally filtered by namespace."""
        entries = self._entries.values()
        if namespace is not None:
            entries = (e for e in entries if e.asset.namespace == namespace)
        return tuple(entries)
