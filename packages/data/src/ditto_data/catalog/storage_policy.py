"""DataCatalog storage-location policy."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_data.catalog.contracts import DataCatalogEntry
from ditto_data.catalog.metadata import DatasetMetadata, default_dataset_metadata

__all__ = ["validate_catalog_storage_location"]


def _storage_prefixes_text(prefixes: tuple[str, ...]) -> str:
    return ", ".join(repr(prefix) for prefix in prefixes)


def validate_catalog_storage_location(
    entry: DataCatalogEntry,
    *,
    registry: Mapping[str, DatasetMetadata] | None = None,
) -> None:
    """Validate a catalog entry against data-owned storage-location metadata."""
    metadata_registry = default_dataset_metadata() if registry is None else registry
    metadata = metadata_registry.get(entry.asset.dataset_id)
    if metadata is None:
        return
    prefixes = metadata.storage_uri_prefixes
    if not prefixes:
        msg = (
            f"DataCatalog storage_uri is not allowed for dataset "
            f"{entry.asset.dataset_id!r}: no storage_uri_prefixes are declared"
        )
        raise ValueError(msg)
    if any(entry.storage_uri.startswith(prefix) for prefix in prefixes):
        return
    msg = (
        f"Invalid DataCatalog storage_uri for dataset {entry.asset.dataset_id!r}: "
        f"{entry.storage_uri!r}; expected one of "
        f"{_storage_prefixes_text(prefixes)}"
    )
    raise ValueError(msg)
