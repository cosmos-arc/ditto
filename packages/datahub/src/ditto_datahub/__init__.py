"""Ditto 数据模块."""

# DataHub Facade 已在 v0.15.0 移除
# Port 层现在直接注入 Domain Services

# 导出 Domain Services（供 Port 层使用）
from ditto_datahub.services.capital import CapitalService
from ditto_datahub.services.factors import FactorService
from ditto_datahub.services.features import FeatureService
from ditto_datahub.services.fundamental import FundamentalService
from ditto_datahub.services.macro import MacroService
from ditto_datahub.services.market import MarketService
from ditto_datahub.services.metadata import MetadataService

__all__ = [
    "CapitalService",
    "FactorService",
    "FeatureService",
    "FundamentalService",
    "MacroService",
    "MarketService",
    "MetadataService",
]
