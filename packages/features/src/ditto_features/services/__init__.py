"""Features services -- derived data services."""

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

__all__ = [
    "COMPARE_RESULT_COLUMNS",
    "LATEST_RESULT_COLUMNS",
    "SERIES_RESULT_COLUMNS",
    "ArtifactMetadataParams",
    "ArtifactPersistenceService",
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
    "DerivedSourceScope",
    "GcConfig",
    "GcPlan",
    "GcReport",
    "MaterializationTaskResult",
    "VersionResolutionStrategy",
    "empty_compare_result",
    "empty_latest_result",
    "empty_series_result",
]
