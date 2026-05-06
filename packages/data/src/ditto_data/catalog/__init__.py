"""Product-neutral data catalog contracts."""

from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    DataCatalogWriter,
    DataSchemaFingerprint,
)

__all__ = [
    "DataAssetRef",
    "DataCatalogEntry",
    "DataCatalogReader",
    "DataCatalogWriter",
    "DataSchemaFingerprint",
]
