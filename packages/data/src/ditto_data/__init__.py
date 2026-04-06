"""Ditto 数据模块 — 数据层统一入口."""

# Data Facade 已在 v0.15.0 移除
# App 层现在直接注入 Domain Services

# 导出 Data Provider Protocol（从 ditto-data 合并）
from ditto_data.events import DataIngested, QualityCheckCompleted
from ditto_data.provider import BarQuery, DataProvider, InstrumentQuery

# 导出 Domain Services（供 App 层使用）
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.derived import DerivedQueryService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService

__all__ = [
    "BarQuery",
    "CapitalService",
    "DataIngested",
    "DataProvider",
    "DerivedQueryService",
    "FundamentalService",
    "InstrumentQuery",
    "MacroService",
    "MarketService",
    "MetadataService",
    "QualityCheckCompleted",
]
