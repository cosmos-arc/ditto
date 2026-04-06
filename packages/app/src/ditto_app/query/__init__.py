"""App Query 模块 — 只读查询，零副作用."""

from __future__ import annotations

from ditto_app.query.capital import CapitalQueryFacade
from ditto_app.query.commodity import CommodityQueryFacade
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
from ditto_app.query.forward_return_service import ForwardReturnService
from ditto_app.query.fundamental import FundamentalQueryFacade
from ditto_app.query.fx import FXQueryFacade
from ditto_app.query.macro import MacroQueryFacade
from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_app.query.research import ResearchDatasetFacade
from ditto_app.query.source import SourceQueryFacade

__all__ = [
    "CapitalQueryFacade",
    "CommodityQueryFacade",
    "DerivedCompareResult",
    "DerivedLatestResult",
    "DerivedQueryFacade",
    "DerivedSeriesResult",
    "EvaluationOptions",
    "FXQueryFacade",
    "FactorEvaluationFacade",
    "ForwardReturnService",
    "FundamentalQueryFacade",
    "LatestDerivedRequest",
    "MacroQueryFacade",
    "MarketQueryFacade",
    "MetadataQueryFacade",
    "ResearchDatasetFacade",
    "RuntimeMode",
    "RuntimeModeResolver",
    "SeriesDerivedRequest",
    "SourceCompareRequest",
    "SourceQueryFacade",
    "StaticRuntimeModeResolver",
]
