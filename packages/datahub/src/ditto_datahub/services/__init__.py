"""
Services module - 域服务统一入口.

本模块提供所有域服务的统一导入，遵循域驱动设计（DDD）原则。

架构原则:
- Service 封装业务逻辑，组合 Store 操作
- Port 层只依赖 Service，不直接访问 Store
- Core 层仅使用 DataHub 模型定义，不依赖 Service

域服务列表:
- MarketService: 市场行情数据查询（K线、复权、状态）
- MetadataService: 元数据查询（证券、日历、行业、标的池）
- FundamentalService: 企业基本面数据（财务报表、分红、业绩预告）
- CapitalService: 资金市场数据（估值、融资融券、股权质押）
- MacroService: 宏观经济指标（经济、利率、汇率、货币供应）
- FeatureService: 技术指标数据（趋势、动量、波动率、成交量）
- FactorService: 因子信号数据（基本面、技术面、宏观、统计）
"""

# Market 域服务
from ditto_datahub.services.capital import CapitalService

# Factors 域服务
from ditto_datahub.services.factors import FactorQuery, FactorService

# Features 域服务
from ditto_datahub.services.features import FeatureQuery, FeatureService

# Fundamental 域服务
from ditto_datahub.services.fundamental import FundamentalService

# Macro 域服务
from ditto_datahub.services.macro import MacroQuery, MacroService
from ditto_datahub.services.market import (
    AdjType,
    MarketBarsQuery,
    MarketConstituentsQuery,
    MarketService,
)

# Metadata 域服务
from ditto_datahub.services.metadata import (
    MetadataQuery,
    MetadataService,
)

__all__ = [
    "AdjType",
    "CapitalService",
    "FactorQuery",
    "FactorService",
    "FeatureQuery",
    "FeatureService",
    "FundamentalService",
    "MacroQuery",
    "MacroService",
    "MarketBarsQuery",
    "MarketConstituentsQuery",
    "MarketService",
    "MetadataQuery",
    "MetadataService",
]
