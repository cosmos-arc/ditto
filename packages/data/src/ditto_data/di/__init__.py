"""
Data 层 DI Provider 聚合。

将所有 Data 层的 Dishka Provider 统一注册，
由 Composition Root（registry/container.py）通过此模块导入。

Providers:
    SourcesProvider: 外部数据源（Tushare、FRED）
    RuntimeProvider: SQLite 基础设施 + CQRS Readers/Writers + 运行时服务
    MetadataProvider: 证券主数据、日历、行业、标的池
    MarketProvider: 股票/ETF/指数行情、状态、复权因子
    FundamentalProvider: 财务报表、股息、公司行动、业绩预告
    CapitalProvider: 保证金、质押、估值、指数成分
    MacroProvider: 宏观经济指标
    DerivedProvider: 衍生查询/缓存基础设施
    GoldenDatasetProvider: 黄金数据集配置
    QualityProvider: DQ 质量引擎
"""

from dishka import Provider

from .builders import parquet_store_pair, sqlite_store_pair
from .capital import CapitalProvider
from .derived import DerivedProvider
from .fundamental import FundamentalProvider
from .golden import GoldenDatasetProvider
from .macro import MacroProvider
from .market import MarketProvider
from .metadata import MetadataProvider
from .quality import QualityProvider
from .runtime import RuntimeProvider
from .sources import SourcesProvider

__all__ = [
    "CapitalProvider",
    "DerivedProvider",
    "FundamentalProvider",
    "GoldenDatasetProvider",
    "MacroProvider",
    "MarketProvider",
    "MetadataProvider",
    "QualityProvider",
    "RuntimeProvider",
    "SourcesProvider",
    "get_data_providers",
    "parquet_store_pair",
    "sqlite_store_pair",
]


def get_data_providers() -> list[Provider]:
    """
    返回 Data 层的所有 Provider.

    包含 Data 层的 10 个 Provider，
    统一由 Data 包管理 DI 注册。
    """
    return [
        SourcesProvider(),
        RuntimeProvider(),
        MetadataProvider(),
        MarketProvider(),
        FundamentalProvider(),
        CapitalProvider(),
        MacroProvider(),
        DerivedProvider(),
        GoldenDatasetProvider(),
        QualityProvider(),
    ]
