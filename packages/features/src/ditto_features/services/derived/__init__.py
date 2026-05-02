"""Unified derived query contracts."""

from ditto_features.services.derived.artifact_reader import (
    DerivedArtifactReader,
    VersionResolutionStrategy,
)
from ditto_features.services.derived.garbage_collector import DerivedGarbageCollector
from ditto_features.services.derived.gc_models import GcConfig, GcPlan, GcReport
from ditto_features.services.derived.queries import (
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedSeriesQuery,
    DerivedSourceScope,
)
from ditto_features.services.derived.query_service import DerivedQueryService
from ditto_features.services.derived.results import (
    COMPARE_RESULT_COLUMNS,
    LATEST_RESULT_COLUMNS,
    SERIES_RESULT_COLUMNS,
    empty_compare_result,
    empty_latest_result,
    empty_series_result,
)

__all__ = [
    "COMPARE_RESULT_COLUMNS",
    "LATEST_RESULT_COLUMNS",
    "SERIES_RESULT_COLUMNS",
    "DerivedArtifactReader",
    "DerivedCompareQuery",
    "DerivedGarbageCollector",
    "DerivedLatestQuery",
    "DerivedQueryService",
    "DerivedSeriesQuery",
    "DerivedSourceScope",
    "GcConfig",
    "GcPlan",
    "GcReport",
    "VersionResolutionStrategy",
    "empty_compare_result",
    "empty_latest_result",
    "empty_series_result",
]
