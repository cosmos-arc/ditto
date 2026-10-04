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

# --- derived: governed spec registration ---
from ditto_features.services.derived.spec_registration import (
    DEFAULT_MATERIALIZABLE_FACTOR_IDS,
    FactorSpecRegistration,
    build_factor_derived_spec,
    factor_spec_hash,
    register_governed_factor,
)

# --- catalog ---
from ditto_features.services.derived_catalog_service import (
    DerivedCatalogReaderProtocol,
    DerivedCatalogService,
    DerivedCatalogWriterProtocol,
)
from ditto_features.storage.derived_artifact_writer import extract_partition_keys

__all__ = [
    "COMPARE_RESULT_COLUMNS",
    "DEFAULT_MATERIALIZABLE_FACTOR_IDS",
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
    "FactorSpecRegistration",
    "GcConfig",
    "GcPlan",
    "GcReport",
    "MaterializationTaskResult",
    "VersionResolutionStrategy",
    "build_factor_derived_spec",
    "empty_compare_result",
    "empty_latest_result",
    "empty_series_result",
    "extract_partition_keys",
    "factor_spec_hash",
    "register_governed_factor",
]
