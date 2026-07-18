"""Product-neutral data catalog contracts."""

from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    DataCatalogWriter,
    DataSchemaFingerprint,
)
from ditto_data.catalog.license import (
    DatasetLicenseDraft,
    DatasetLicenseReader,
    DatasetLicenseRecord,
    DatasetLicenseWriter,
)
from ditto_data.catalog.metadata import (
    DatasetMetadata,
    DatasetProductContract,
    default_dataset_metadata,
)
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
    ProviderSnapshotReader,
    ProviderSnapshotWriter,
)
from ditto_data.catalog.store import InMemoryDataCatalog

__all__ = [
    "DataAssetRef",
    "DataCatalogEntry",
    "DataCatalogReader",
    "DataCatalogWriter",
    "DataSchemaFingerprint",
    "DatasetLicenseDraft",
    "DatasetLicenseReader",
    "DatasetLicenseRecord",
    "DatasetLicenseWriter",
    "DatasetMetadata",
    "DatasetProductContract",
    "InMemoryDataCatalog",
    "ProviderSnapshot",
    "ProviderSnapshotDraft",
    "ProviderSnapshotReader",
    "ProviderSnapshotWriter",
    "default_dataset_metadata",
]
