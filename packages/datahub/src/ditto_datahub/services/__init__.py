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
- SourceService: 外部数据源访问（Tushare 等）
- IngestionLogService: 数据摄入日志管理（追踪摄入状态、失败重试）
- QualityRecordService: 质量记录服务（对比结果、隔离数据）
"""

# Capital 域服务
from ditto_datahub.services.capital_service import CapitalService

# Factors 域服务
from ditto_datahub.services.factor_service import FactorQuery, FactorService

# Features 域服务
from ditto_datahub.services.feature_service import FeatureQuery, FeatureService

# Fundamental 域服务
from ditto_datahub.services.fundamental_service import FundamentalService

# Runtime 服务
from ditto_datahub.services.ingestion_log_service import IngestionLogService

# Macro 域服务
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import (
    AdjType,
    MarketBarsQuery,
    MarketConstituentsQuery,
    MarketService,
)

# Metadata 域服务
from ditto_datahub.services.metadata_service import MetadataService

# Ports 对象（用于 DI 容器组装）
from ditto_datahub.services.ports import (
    FundamentalReadPorts,
    FundamentalWritePorts,
    MarketReadPorts,
    MarketWritePorts,
)
from ditto_datahub.services.quality_record_service import QualityRecordService

# Source 服务
from ditto_datahub.services.source_service import SourceService

__all__ = [
    "AdjType",
    "CapitalService",
    "FactorQuery",
    "FactorService",
    "FeatureQuery",
    "FeatureService",
    "FundamentalReadPorts",
    "FundamentalService",
    "FundamentalWritePorts",
    "IngestionLogService",
    "MacroService",
    "MarketBarsQuery",
    "MarketConstituentsQuery",
    "MarketReadPorts",
    "MarketService",
    "MarketWritePorts",
    "MetadataService",
    "QualityRecordService",
    "SourceService",
]
