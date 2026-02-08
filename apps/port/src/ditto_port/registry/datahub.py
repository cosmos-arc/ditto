"""
DataHub 组件注册.

Root 注入模式：在 Provider 中集中注册所有 DataHub 组件。
所有依赖通过 Provider 管理，DataHub 不再使用 @cached_property.

架构说明：
- Store 的导入和创建已移至 DomainServiceProvider
- DataHubProvider 只负责组合 Domain Services
- Port 层不再直接依赖 Store 类
"""

# 延迟类型注解评估，避免前向引用问题
from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub import DataHub
from ditto_datahub.config.data_root import DataRootConfig
from ditto_datahub.domains.capital import CapitalService
from ditto_datahub.domains.capital.capital_store import CapitalStore
from ditto_datahub.domains.factors import FactorService
from ditto_datahub.domains.factors.factor_metadata_store import (
    FactorMetadataStore,
)
from ditto_datahub.domains.factors.factor_store import FactorStore
from ditto_datahub.domains.features import FeatureService
from ditto_datahub.domains.features.technical import (
    IndicatorMetadataStore as FeatureIndicatorMetadataStore,
)
from ditto_datahub.domains.features.technical import (
    IndicatorStore as FeatureIndicatorStore,
)
from ditto_datahub.domains.fundamental import FundamentalService
from ditto_datahub.domains.fundamental.fundamental_store import (
    FundamentalStore,
)
from ditto_datahub.domains.macro import MacroService
from ditto_datahub.domains.macro.indicator.indicator_store import (
    IndicatorStore as MacroIndicatorStore,
)
from ditto_datahub.domains.macro.indicator.metadata_store import (
    IndicatorMetadataStore as MacroIndicatorMetadataStore,
)
from ditto_datahub.domains.market import MarketService
from ditto_datahub.domains.market.etf.adj import EtfAdjFactorStore
from ditto_datahub.domains.market.etf.bars import EtfBarsStore
from ditto_datahub.domains.market.etf.nav import EtfNavStore
from ditto_datahub.domains.market.etf.status import EtfStatusStore
from ditto_datahub.domains.market.index.bars import IndexBarsStore
from ditto_datahub.domains.market.index.constituent import (
    IndexConstituentStore,
)
from ditto_datahub.domains.market.stock.adj import StockAdjFactorStore
from ditto_datahub.domains.market.stock.bars import StockBarsStore
from ditto_datahub.domains.market.stock.status import StockStatusStore
from ditto_datahub.domains.metadata import MetadataService
from ditto_datahub.domains.metadata.calendar.calendar_store import (
    CalendarStore as MetadataCalendarStore,
)
from ditto_datahub.domains.metadata.identity.identity_store import (
    IdentityStore,
)
from ditto_datahub.domains.metadata.industry.industry_basic_store import (
    IndustryBasicStore,
)
from ditto_datahub.domains.metadata.industry.industry_mapping_store import (
    IndustryMappingStore,
)
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.domains.metadata.instrument.instrument_store import (
    InstrumentStore as MetadataInstrumentStore,
)
from ditto_datahub.domains.metadata.universe import UniverseStore
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tushare.tushare_source import TushareSource
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool
from ditto_foundation.concurrency import FileLockManager

__all__ = ["DataHubProvider"]


class DataHubProvider(Provider):
    """
    DataHub 组件 Provider.

    架构说明：
    - Store 的创建由 DomainServiceProvider 负责
    - 此 Provider 只负责组合 Domain Services
    - Store 依赖通过 dishka 容器自动注入
    """

    scope = Scope.APP

    @provide
    def data_root(self, config: DataRootConfig) -> Path:
        """数据根目录."""
        return config.data_root

    # ========================================================================
    # Runtime Layer
    # ========================================================================

    @provide
    def sqlite_pool(
        self,
        config: DataRootConfig,
    ) -> Iterator[SQLitePool]:
        """SQLite 连接池（应用级单例）."""
        db_path = config.metadata_db_path
        # 确保父目录存在
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # 获取 schema.sql 路径
        # 将 Traversable 转换为 Path（importlib.resources.files 返回 Traversable）
        schema_traversable = files("ditto_datahub.scripts") / "schema.sql"
        schema_path = Path(str(schema_traversable))
        pool = SQLitePool(str(db_path), schema_path=schema_path)
        pool.init_schema()
        yield pool
        pool.close()

    @provide
    def file_lock(self, data_root: Path) -> FileLockManager:
        """文件锁管理器."""
        lock_dir = data_root / "locks"
        return FileLockManager(lock_dir)

    # ========================================================================
    # Fundamental & Capital Query Services
    # ========================================================================

    @provide
    def fundamental_query_service(
        self,
        fundamental_store: FundamentalStore,
    ) -> FundamentalService:
        """Fundamental 查询服务."""
        return FundamentalService(fundamental_store=fundamental_store)

    @provide
    def capital_query_service(
        self,
        capital_store: CapitalStore,
    ) -> CapitalService:
        """Capital 查询服务."""
        return CapitalService(capital_store=capital_store)

    # ========================================================================
    # Macro Query Service
    # ========================================================================

    @provide
    def macro_query_service(
        self,
        macro_indicator_store: MacroIndicatorStore,
        macro_metadata_store: MacroIndicatorMetadataStore,
    ) -> MacroService:
        """Macro 查询服务."""
        return MacroService(
            indicator_store=macro_indicator_store,
            metadata_store=macro_metadata_store,
        )

    # ========================================================================
    # Features Domain Stores & Services
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

    @provide
    def features_query_service(
        self,
        feature_indicator_store: FeatureIndicatorStore,
        feature_indicator_metadata_store: FeatureIndicatorMetadataStore,
    ) -> FeatureService:
        """Features 查询服务."""
        return FeatureService(
            indicator_store=feature_indicator_store,
            metadata_store=feature_indicator_metadata_store,
        )

    # ========================================================================
    # Factors Domain Stores & Services
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

    @provide
    def factors_query_service(
        self,
        factor_store: FactorStore,
        factor_metadata_store: FactorMetadataStore,
    ) -> FactorService:
        """Factors 查询服务."""
        return FactorService(
            factor_store=factor_store,
            metadata_store=factor_metadata_store,
        )

    # ========================================================================
    # Metadata Query Service
    # ========================================================================

    @provide
    def metadata_query_service(
        self,
        instrument_store: MetadataInstrumentStore,
        identity_store: IdentityStore,
        calendar_store: MetadataCalendarStore,
        industry_basic_store: IndustryBasicStore,
        industry_mapping_store: IndustryMappingStore,
        universe_store: UniverseStore,
        instrument_id_allocator: InstrumentIdAllocator,
    ) -> MetadataService:
        """Metadata 查询服务."""
        return MetadataService(
            instrument_store=instrument_store,
            identity_store=identity_store,
            calendar_store=calendar_store,
            industry_basic_store=industry_basic_store,
            industry_mapping_store=industry_mapping_store,
            universe_store=universe_store,
            instrument_id_allocator=instrument_id_allocator,
        )

    # ========================================================================
    # Market Query Service
    # ========================================================================

    @provide
    def market_query_service(  # noqa: PLR0913
        self,
        stock_bars_store: StockBarsStore,
        stock_status_store: StockStatusStore,
        stock_adj_store: StockAdjFactorStore,
        etf_bars_store: EtfBarsStore,
        etf_status_store: EtfStatusStore,
        instrument_store: MetadataInstrumentStore,
        file_lock_manager: FileLockManager,
        etf_nav_store: EtfNavStore,
        etf_adj_store: EtfAdjFactorStore,
        index_bars_store: IndexBarsStore,
        index_constituent_store: IndexConstituentStore,
    ) -> MarketService:
        """Market 查询服务（支持读写）。"""
        return MarketService(
            stock_bars_store=stock_bars_store,
            stock_status_store=stock_status_store,
            stock_adj_store=stock_adj_store,
            etf_bars_store=etf_bars_store,
            etf_status_store=etf_status_store,
            instrument_store=instrument_store,
            file_lock=file_lock_manager,
            etf_nav_store=etf_nav_store,
            etf_adj_store=etf_adj_store,
            index_bars_store=index_bars_store,
            index_constituent_store=index_constituent_store,
        )

    # ========================================================================
    # Sources Layer
    # ========================================================================

    @provide
    def sources(self, tushare_source: TushareSource) -> DataSources:
        """
        外部数据源组合器.

        Args:
            tushare_source: Tushare 数据源实例

        """
        return DataSources(tushare=tushare_source)

    # ========================================================================
    # SQL Engine
    # ========================================================================

    @provide
    def sql_engine(
        self,
        data_root: Path,
        instrument_store: InstrumentStore,
        calendar_store: MetadataCalendarStore,
    ) -> SqlEngine:
        """DuckDB SQL 引擎."""
        return SqlEngine(
            data_root=data_root,
            instrument_store=instrument_store,
            calendar_store=calendar_store,
        )

    # ========================================================================
    # DataHub
    # ========================================================================

    @provide
    def datahub(  # noqa: PLR0913
        self,
        data_root: Path,
        sqlite_pool: SQLitePool,
        file_lock: FileLockManager,
        instrument_id_allocator: InstrumentIdAllocator,
        freeze_manager: FreezeManager,
        instrument_store: InstrumentStore,
        metadata_query_service: MetadataService,
        market_query_service: MarketService,
        fundamental_query_service: FundamentalService,
        capital_query_service: CapitalService,
        macro_query_service: MacroService,
        features_query_service: FeatureService,
        factors_query_service: FactorService,
        ingestion_log_store: IngestionLogStore,
        sources: DataSources,
        sql_engine: SqlEngine,
    ) -> Iterator[DataHub]:
        """
        DataHub 主入口（应用级单例）.

        所有依赖通过 Provider 注入，DataHub 不再使用 @cached_property.
        移除了 Accessor 层，直接使用 Domain Services.
        """
        # 创建 DataHub 并注入所有依赖
        hub = DataHub(
            data_root=data_root,
            sqlite_pool=sqlite_pool,
            file_lock=file_lock,
            instrument_id_allocator=instrument_id_allocator,
            freeze_manager=freeze_manager,
            instrument_store=instrument_store,
            metadata_query_service=metadata_query_service,
            market_query_service=market_query_service,
            fundamental_query_service=fundamental_query_service,
            capital_query_service=capital_query_service,
            macro_query_service=macro_query_service,
            features_query_service=features_query_service,
            factors_query_service=factors_query_service,
            ingestion_log_store=ingestion_log_store,
            sources=sources,
            sql_engine=sql_engine,
        )

        yield hub

        # 关闭 sqlite_pool
        sqlite_pool.close()
