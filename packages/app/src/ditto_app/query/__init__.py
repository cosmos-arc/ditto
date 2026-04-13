"""App Query 模块 — 只读查询，零副作用."""

from __future__ import annotations

from ditto_app.query.backtest import BacktestQueryFacade
from ditto_app.query.backtest_trade import BacktestTradeQueryFacade
from ditto_app.query.capital import CapitalQueryFacade
from ditto_app.query.commodity import CommodityQueryFacade
from ditto_app.query.comparison import ComparisonQueryFacade
from ditto_app.query.derived import (
    DerivedCompareResult,
    DerivedLatestResult,
    DerivedQueryFacade,
    DerivedSeriesResult,
    LatestDerivedRequest,
    SeriesDerivedRequest,
    SourceCompareRequest,
)
from ditto_app.query.evaluation import EvaluationOptions, FactorEvaluationFacade
from ditto_app.query.forward_return_service import ForwardReturnService
from ditto_app.query.fundamental import FundamentalQueryFacade
from ditto_app.query.fx import FXQueryFacade
from ditto_app.query.lineage import LineageChain, LineageQueryFacade
from ditto_app.query.macro import MacroQueryFacade
from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_app.query.portfolio_actual import PnlSummary, PortfolioActualQueryFacade
from ditto_app.query.research import ResearchDatasetFacade
from ditto_app.query.run import RunReadModel
from ditto_app.query.signal import SignalQueryFacade
from ditto_app.query.source import SourceQueryFacade
from ditto_app.query.strategy import StrategyQueryFacade
from ditto_app.query.trade import TradeQueryFacade

__all__ = [
    "BacktestQueryFacade",
    "BacktestTradeQueryFacade",
    "CapitalQueryFacade",
    "CommodityQueryFacade",
    "ComparisonQueryFacade",
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
    "LineageChain",
    "LineageQueryFacade",
    "MacroQueryFacade",
    "MarketQueryFacade",
    "MetadataQueryFacade",
    "PnlSummary",
    "PortfolioActualQueryFacade",
    "ResearchDatasetFacade",
    "RunReadModel",
    "SeriesDerivedRequest",
    "SignalQueryFacade",
    "SourceCompareRequest",
    "SourceQueryFacade",
    "StrategyQueryFacade",
    "TradeQueryFacade",
]
