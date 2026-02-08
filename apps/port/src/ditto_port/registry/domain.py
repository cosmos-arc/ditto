"""
Domain Store Provider - 封装所有 Store 的导入和创建.

将所有 DataHub Store 类的导入和创建逻辑封装在此 Provider 中，
避免 DataHubProvider 直接依赖具体的 Store 类。

架构分层：
    Port 层 (apps/port) → DomainServiceProvider → DataHub Store 层
"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_root import DataRootConfig
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.quality.quarantine_store import QuarantineStore
from ditto_datahub.stores.capital.capital_store import CapitalStore
from ditto_datahub.stores.factors.factor_metadata_store import (
    FactorMetadataStore,
)
from ditto_datahub.stores.factors.factor_store import FactorStore
from ditto_datahub.stores.features.technical import (
    IndicatorMetadataStore as FeatureIndicatorMetadataStore,
)
from ditto_datahub.stores.features.technical import (
    IndicatorStore as FeatureIndicatorStore,
)
from ditto_datahub.stores.fundamental.fundamental_store import FundamentalStore
from ditto_datahub.stores.macro.indicator.indicator_store import (
    IndicatorStore as MacroIndicatorStore,
)
from ditto_datahub.stores.macro.indicator.metadata_store import (
    IndicatorMetadataStore as MacroIndicatorMetadataStore,
)
from ditto_datahub.stores.market.etf.adj import EtfAdjFactorStore
from ditto_datahub.stores.market.etf.bars import EtfBarsStore
from ditto_datahub.stores.market.etf.nav import EtfNavStore
from ditto_datahub.stores.market.etf.status import EtfStatusStore
from ditto_datahub.stores.market.index.bars import IndexBarsStore
from ditto_datahub.stores.market.index.constituent import IndexConstituentStore
from ditto_datahub.stores.market.stock.adj import StockAdjFactorStore
from ditto_datahub.stores.market.stock.bars import StockBarsStore
from ditto_datahub.stores.market.stock.status import StockStatusStore
from ditto_datahub.stores.metadata.calendar.calendar_store import (
    CalendarStore as MetadataCalendarStore,
)
from ditto_datahub.stores.metadata.identity.identity_store import IdentityStore
from ditto_datahub.stores.metadata.industry.industry_basic_store import (
    IndustryBasicStore,
)
from ditto_datahub.stores.metadata.industry.industry_mapping_store import (
    IndustryMappingStore,
)
from ditto_datahub.stores.metadata.instrument import InstrumentStore
from ditto_datahub.stores.metadata.universe import UniverseStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool

__all__ = ["DomainServiceProvider"]


class DomainServiceProvider(Provider):
    """
    Domain Store Provider - 封装所有 Store 的创建.

    职责：
    - 导入所有 DataHub Store 类（封装在此文件中）
    - 提供 Store 实例的创建方法
    - 通过 dishka 容器管理依赖注入
    """

    scope = Scope.APP

    # ========================================================================
    # Runtime Layer
    # ========================================================================

    @provide
    def sqlite_client(self, sqlite_pool: SQLitePool) -> SQLiteClient:
        """SQLite 客户端（基于全局连接池）."""
        return SQLiteClient(sqlite_pool)

    @provide
    def instrument_id_allocator(self, sqlite_pool: SQLitePool) -> InstrumentIdAllocator:
        """Instrument ID 分配器."""
        return InstrumentIdAllocator(sqlite_pool)

    @provide
    def freeze_manager(self, data_root: Path) -> FreezeManager:
        """数据版本管理."""
        return FreezeManager(data_root=str(data_root))

    # ========================================================================
    # Metadata Domain Stores
    # ========================================================================

    @provide
    def instrument_store(self, sqlite_client: SQLiteClient) -> InstrumentStore:
        """证券数据存储."""
        return InstrumentStore(sqlite_client)

    @provide
    def calendar_store(self, sqlite_client: SQLiteClient) -> MetadataCalendarStore:
        """交易日历存储."""
        return MetadataCalendarStore(sqlite_client)

    @provide
    def identity_store(self, config: DataRootConfig) -> IdentityStore:
        """Identity 映射存储."""
        return IdentityStore(config.metadata_db_path)

    @provide
    def industry_basic_store(
        self,
        config: DataRootConfig,
    ) -> IndustryBasicStore:
        """行业主数据存储."""
        return IndustryBasicStore(config.metadata_db_path)

    @provide
    def industry_mapping_store(
        self,
        config: DataRootConfig,
    ) -> IndustryMappingStore:
        """行业映射存储."""
        return IndustryMappingStore(config.metadata_db_path)

    @provide
    def universe_store(self, sqlite_client: SQLiteClient) -> UniverseStore:
        """证券池存储."""
        return UniverseStore(sqlite_client)

    @provide
    def ingestion_log_store(self, sqlite_client: SQLiteClient) -> IngestionLogStore:
        """摄取日志存储."""
        return IngestionLogStore(sqlite_client)

    @provide
    def quarantine_store(self, sqlite_client: SQLiteClient) -> QuarantineStore:
        """隔离区存储（使用主数据库）."""
        return QuarantineStore(sqlite_client)

    # ========================================================================
    # Market Domain Stores
    # ========================================================================

    @provide
    def stock_bars_store(self, config: DataRootConfig) -> StockBarsStore:
        """股票 K线存储."""
        return StockBarsStore(config.data_root)

    @provide
    def stock_status_store(self, config: DataRootConfig) -> StockStatusStore:
        """股票状态存储."""
        return StockStatusStore(config.data_root)

    @provide
    def stock_adj_store(self, config: DataRootConfig) -> StockAdjFactorStore:
        """股票复权因子存储."""
        return StockAdjFactorStore(config.data_root)

    @provide
    def etf_bars_store(self, config: DataRootConfig) -> EtfBarsStore:
        """ETF K线存储."""
        return EtfBarsStore(config.data_root)

    @provide
    def etf_status_store(self, config: DataRootConfig) -> EtfStatusStore:
        """ETF 状态存储."""
        return EtfStatusStore(config.data_root)

    @provide
    def etf_nav_store(self, config: DataRootConfig) -> EtfNavStore:
        """ETF 净值存储."""
        return EtfNavStore(config.data_root)

    @provide
    def etf_adj_store(self, config: DataRootConfig) -> EtfAdjFactorStore:
        """ETF 复权因子存储."""
        return EtfAdjFactorStore(config.data_root)

    @provide
    def index_bars_store(self, config: DataRootConfig) -> IndexBarsStore:
        """指数 K线存储."""
        return IndexBarsStore(config.data_root)

    @provide
    def index_constituent_store(self, config: DataRootConfig) -> IndexConstituentStore:
        """指数成分股存储."""
        return IndexConstituentStore(config.data_root)

    # ========================================================================
    # Fundamental & Capital Domain Stores
    # ========================================================================

    @provide
    def fundamental_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> FundamentalStore:
        """Fundamental domain data storage."""
        return FundamentalStore(sqlite_client)

    @provide
    def capital_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> CapitalStore:
        """Capital domain data storage."""
        return CapitalStore(sqlite_client)

    # ========================================================================
    # Macro Domain Stores
    # ========================================================================

    @provide
    def macro_indicator_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorStore:
        """Macro indicator data storage."""
        return MacroIndicatorStore(sqlite_client)

    @provide
    def macro_metadata_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorMetadataStore:
        """Macro indicator metadata storage."""
        return MacroIndicatorMetadataStore(sqlite_client)

    # ========================================================================
    # Features Domain Stores
    # ========================================================================

    @provide
    def feature_indicator_store(
        self,
        data_root_config: DataRootConfig,
    ) -> FeatureIndicatorStore:
        """Feature technical indicator storage."""
        return FeatureIndicatorStore(
            data_root_config.features_technical_indicators_narrow_path
        )

    @provide
    def feature_indicator_metadata_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> FeatureIndicatorMetadataStore:
        """Feature indicator metadata storage."""
        return FeatureIndicatorMetadataStore(sqlite_client)

    # ========================================================================
    # Factors Domain Stores
    # ========================================================================

    @provide
    def factor_store(
        self,
        data_root_config: DataRootConfig,
    ) -> FactorStore:
        """Factor data storage."""
        return FactorStore(data_root_config.factors_narrow_path)

    @provide
    def factor_metadata_store(
        self,
        sqlite_client: SQLiteClient,
    ) -> FactorMetadataStore:
        """Factor metadata storage."""
        return FactorMetadataStore(sqlite_client)
