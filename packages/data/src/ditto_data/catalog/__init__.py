"""Product-neutral data catalog contracts."""

from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    DataCatalogWriter,
    DataSchemaFingerprint,
)
from ditto_data.catalog.metadata import (
    DatasetMetadata,
    default_dataset_metadata,
)
from ditto_data.catalog.store import InMemoryDataCatalog

__all__ = [
    "DataAssetRef",
    "DataCatalogEntry",
    "DataCatalogReader",
    "DataCatalogWriter",
    "DataSchemaFingerprint",
    "DatasetMetadata",
    "InMemoryDataCatalog",
    "default_dataset_metadata",
]
