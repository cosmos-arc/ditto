"""App Query 模块 — 只读查询，零副作用."""

from ditto_app.query.derived import (
    DerivedCompareResult,
    DerivedLatestResult,
    DerivedQueryFacade,
    DerivedSeriesResult,
    LatestDerivedRequest,
    RuntimeMode,
    RuntimeModeResolver,
    SeriesDerivedRequest,
    SourceCompareRequest,
    StaticRuntimeModeResolver,
)
from ditto_app.query.evaluation import EvaluationOptions, FactorEvaluationFacade
from ditto_app.query.research import ResearchDatasetFacade

__all__ = [
    "DerivedCompareResult",
    "DerivedLatestResult",
    "DerivedQueryFacade",
    "DerivedSeriesResult",
    "EvaluationOptions",
    "FactorEvaluationFacade",
    "LatestDerivedRequest",
    "ResearchDatasetFacade",
    "RuntimeMode",
    "RuntimeModeResolver",
    "SeriesDerivedRequest",
    "SourceCompareRequest",
    "StaticRuntimeModeResolver",
]
