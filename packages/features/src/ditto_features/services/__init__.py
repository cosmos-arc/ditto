"""Features services -- derived data services and publication safety."""

# --- derived: query types & helpers ---
from ditto_features.services.derived import (
    COMPARE_RESULT_COLUMNS,
    LATEST_RESULT_COLUMNS,
    SERIES_RESULT_COLUMNS,
    DerivedArtifactFrameRequest,
    DerivedArtifactReader,
    DerivedCompareQuery,
    DerivedGarbageCollector,
    DerivedLatestQuery,
    DerivedQueryService,
    DerivedSeriesQuery,
    DerivedSourceScope,
    GcConfig,
    GcPlan,
    GcReport,
    VersionResolutionStrategy,
    empty_compare_result,
    empty_latest_result,
    empty_series_result,
)

# --- derived: artifact persistence ---
from ditto_features.services.derived.artifact_persistence_service import (
    ArtifactMetadataParams,
    ArtifactMetadataUpdateParams,
    ArtifactPersistenceService,
)

# --- derived: concurrent materialization ---
from ditto_features.services.derived.concurrent_materializer import (
    ConcurrentMaterializer,
    MaterializationTaskResult,
)

# --- catalog ---
from ditto_features.services.derived_catalog_service import (
    DerivedCatalogReaderProtocol,
    DerivedCatalogService,
    DerivedCatalogWriterProtocol,
)

# --- shadow slot ---
from ditto_features.services.derived_shadow_slot_service import (
    DerivedShadowSlotReaderProtocol,
    DerivedShadowSlotService,
    DerivedShadowSlotWriterProtocol,
)

# --- publication safety ---
from ditto_features.services.publication_safety_record_service import (
    CertificationReaderProtocol,
    CertificationWriterProtocol,
    ManifestReaderProtocol,
    ManifestWriterProtocol,
    MinimalDQReaderProtocol,
    MinimalDQWriterProtocol,
    PublicationSafetyRecordService,
    PublicationSafetyRuntimeStores,
    ShadowReportReaderProtocol,
    ShadowReportWriterProtocol,
)

__all__ = [
    "COMPARE_RESULT_COLUMNS",
    "LATEST_RESULT_COLUMNS",
    "SERIES_RESULT_COLUMNS",
    "ArtifactMetadataParams",
    "ArtifactMetadataUpdateParams",
    "ArtifactPersistenceService",
    "CertificationReaderProtocol",
    "CertificationWriterProtocol",
    "ConcurrentMaterializer",
    "DerivedArtifactFrameRequest",
    "DerivedArtifactReader",
    "DerivedCatalogReaderProtocol",
    "DerivedCatalogService",
    "DerivedCatalogWriterProtocol",
    "DerivedCompareQuery",
    "DerivedGarbageCollector",
    "DerivedLatestQuery",
    "DerivedQueryService",
    "DerivedSeriesQuery",
    "DerivedShadowSlotReaderProtocol",
    "DerivedShadowSlotService",
    "DerivedShadowSlotWriterProtocol",
    "DerivedSourceScope",
    "GcConfig",
    "GcPlan",
    "GcReport",
    "ManifestReaderProtocol",
    "ManifestWriterProtocol",
    "MaterializationTaskResult",
    "MinimalDQReaderProtocol",
    "MinimalDQWriterProtocol",
    "PublicationSafetyRecordService",
    "PublicationSafetyRuntimeStores",
    "ShadowReportReaderProtocol",
    "ShadowReportWriterProtocol",
    "VersionResolutionStrategy",
    "empty_compare_result",
    "empty_latest_result",
    "empty_series_result",
]
