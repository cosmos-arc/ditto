"""
DataHub 组件注册.

Root 注入模式：在 Provider 中集中注册所有 DataHub 组件。
所有依赖通过 Provider 管理，DataHub 不再使用 @cached_property.
"""

# 延迟类型注解评估，避免前向引用问题
from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub import DataHub
from ditto_datahub.accessors.adj_factor_accessor import AdjFactorAccessor
from ditto_datahub.accessors.bars_accessor import BarsAccessor
from ditto_datahub.accessors.calendar_accessor import CalendarAccessor
from ditto_datahub.accessors.index_accessor import IndexAccessor
from ditto_datahub.accessors.ingestion_log_accessor import IngestionLogAccessor
from ditto_datahub.accessors.instrument_accessor import InstrumentsAccessor
from ditto_datahub.accessors.quarantine_accessor import QuarantineAccessor
from ditto_datahub.accessors.universe_accessor import UniverseAccessor
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
from ditto_datahub.domains.fundamental.fundamental_store import FundamentalStore
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
from ditto_datahub.domains.market.index.constituent import IndexConstituentStore
from ditto_datahub.domains.market.stock.adj import StockAdjFactorStore
from ditto_datahub.domains.market.stock.bars import StockBarsStore
from ditto_datahub.domains.market.stock.status import StockStatusStore
from ditto_datahub.domains.metadata import MetadataService
from ditto_datahub.domains.metadata.calendar.calendar_store import (
    CalendarStore as MetadataCalendarStore,
)
from ditto_datahub.domains.metadata.identity.identity_store import IdentityStore
from ditto_datahub.domains.metadata.industry.industry_basic_store import (
    IndustryBasicStore,
)
from ditto_datahub.domains.metadata.industry.industry_mapping_store import (
    IndustryMappingStore,
)

# Type aliases for backward compatibility
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.domains.metadata.instrument.instrument_store import (
    InstrumentStore as MetadataInstrumentStore,
)
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tushare.tushare_source import TushareSource
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.universe_store import UniverseStore
from ditto_foundation import SQLitePool
from ditto_foundation.concurrency import FileLockManager

__all__ = ["DataHubProvider"]


class DataHubProvider(Provider):
    """DataHub 组件 Provider."""

    scope = Scope.APP

    @provide
    def data_root_config(self) -> DataRootConfig:
        """数据根配置（从环境变量读取）."""
        return DataRootConfig()

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

    @provide
    def sid_allocator(self, sqlite_pool: SQLitePool) -> SidAllocator:
        """SID 分配器."""
        return SidAllocator(sqlite_pool)

    @provide
    def freeze_manager(self, data_root: Path) -> FreezeManager:
        """数据版本管理."""
        return FreezeManager(data_root=str(data_root))

    # ========================================================================
    # Store Layer
    # ========================================================================

    @provide
    def sqlite_client(self, sqlite_pool: SQLitePool) -> SQLiteClient:
        """SQLite 客户端."""
        return SQLiteClient(sqlite_pool)

    @provide
    def instrument_store(self, sqlite_client: SQLiteClient) -> InstrumentStore:
        """证券数据存储."""
        return InstrumentStore(sqlite_client)

    @provide
    def calendar_store(self, sqlite_client: SQLiteClient) -> MetadataCalendarStore:
        """交易日历存储."""
        return MetadataCalendarStore(sqlite_client)

    @provide
    def bars_store(self, data_root: Path) -> BarsStore:
        """OHLCV 数据存储."""
        return BarsStore(data_root=data_root)

    @provide
    def adj_factor_store(self, data_root: Path) -> AdjFactorStore:
        """复权因子存储（已弃用，建议使用 stock_adj_store）."""
        return AdjFactorStore(data_root=data_root)

    @provide
    def universe_store(self, sqlite_client: SQLiteClient) -> UniverseStore:
        """证券集合存储."""
        return UniverseStore(sqlite_client)

    @provide
    def index_weight_store(self, sqlite_client: SQLiteClient) -> IndexWeightStore:
        """指数权重存储."""
        return IndexWeightStore(sqlite_client)

    @provide
    def ingestion_log_store(self, sqlite_client: SQLiteClient) -> IngestionLogStore:
        """摄取日志存储."""
        return IngestionLogStore(sqlite_client)

    @provide
    def quarantine_store(self, sqlite_client: SQLiteClient) -> QuarantineStore:
        """隔离区存储（使用主数据库）."""
        return QuarantineStore(sqlite_client)

    # ========================================================================
    # Metadata Domain Stores
    # ========================================================================

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
    # Accessor Layer
    # ========================================================================

    @provide
    def securities(
        self,
        instrument_store: InstrumentStore,
        sid_allocator: SidAllocator,
    ) -> InstrumentsAccessor:
        """证券数据访问器（带数据摄入辅助方法）."""
        return InstrumentsAccessor(
            instrument_store=instrument_store,
            sid_allocator=sid_allocator,
        )

    @provide
    def calendar(self, calendar_store: MetadataCalendarStore) -> CalendarAccessor:
        """交易日历访问器."""
        return CalendarAccessor(calendar_store=calendar_store)

    @provide
    def adj_factor(
        self,
        adj_factor_store: AdjFactorStore,
        file_lock: FileLockManager,
    ) -> AdjFactorAccessor:
        """复权因子访问器."""
        return AdjFactorAccessor(
            adj_factor_store=adj_factor_store,
            file_lock=file_lock,
        )

    @provide
    def bars(
        self,
        bars_store: BarsStore,
        instrument_store: InstrumentStore,
        adj_factor_store: AdjFactorStore,
        stock_status_store: StockStatusStore,
        file_lock: FileLockManager,
    ) -> BarsAccessor:
        """OHLCV 数据访问器."""
        return BarsAccessor(
            bars_store=bars_store,
            instrument_store=instrument_store,
            adj_factor_store=adj_factor_store,
            stock_status_store=stock_status_store,
            file_lock=file_lock,
        )

    @provide
    def universe(
        self,
        universe_store: UniverseStore,
        instrument_store: InstrumentStore,
        sid_allocator: SidAllocator,
    ) -> UniverseAccessor:
        """证券集合访问器."""
        return UniverseAccessor(
            universe_store=universe_store,
            instrument_store=instrument_store,
            sid_allocator=sid_allocator,
        )

    @provide
    def index(
        self,
        bars_store: BarsStore,
        index_weight_store: IndexWeightStore,
        instrument_store: InstrumentStore,
    ) -> IndexAccessor:
        """指数数据访问器."""
        return IndexAccessor(
            bars_store=bars_store,
            index_weight_store=index_weight_store,
            instrument_store=instrument_store,
        )

    @provide
    def ingestion_log(
        self,
        ingestion_log_store: IngestionLogStore,
    ) -> IngestionLogAccessor:
        """摄取日志访问器."""
        return IngestionLogAccessor(ingestion_log_store=ingestion_log_store)

    @provide
    def quarantine(
        self,
        quarantine_store: QuarantineStore,
    ) -> QuarantineAccessor:
        """隔离区访问器."""
        return QuarantineAccessor(quarantine_store=quarantine_store)

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
        sid_allocator: SidAllocator,
    ) -> MetadataService:
        """Metadata 查询服务."""
        return MetadataService(
            instrument_store=instrument_store,
            identity_store=identity_store,
            calendar_store=calendar_store,
            industry_basic_store=industry_basic_store,
            industry_mapping_store=industry_mapping_store,
            universe_store=universe_store,
            sid_allocator=sid_allocator,
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
        etf_nav_store: EtfNavStore,
        etf_adj_store: EtfAdjFactorStore,
        index_bars_store: IndexBarsStore,
        index_constituent_store: IndexConstituentStore,
        instrument_store: MetadataInstrumentStore,
    ) -> MarketService:
        """Market 查询服务."""
        return MarketService(
            stock_bars_store=stock_bars_store,
            stock_status_store=stock_status_store,
            stock_adj_store=stock_adj_store,
            etf_bars_store=etf_bars_store,
            etf_status_store=etf_status_store,
            etf_nav_store=etf_nav_store,
            etf_adj_store=etf_adj_store,
            index_bars_store=index_bars_store,
            index_constituent_store=index_constituent_store,
            instrument_store=instrument_store,
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
        sid_allocator: SidAllocator,
        freeze_manager: FreezeManager,
        instrument_store: InstrumentStore,
        securities: InstrumentsAccessor,
        metadata_query_service: MetadataService,
        market_query_service: MarketService,
        fundamental_query_service: FundamentalService,
        capital_query_service: CapitalService,
        macro_query_service: MacroService,
        features_query_service: FeatureService,
        factors_query_service: FactorService,
        calendar: CalendarAccessor,
        adj_factor: AdjFactorAccessor,
        bars: BarsAccessor,
        universe: UniverseAccessor,
        index: IndexAccessor,
        ingestion_log: IngestionLogAccessor,
        quarantine: QuarantineAccessor,
        sources: DataSources,
        sql_engine: SqlEngine,
    ) -> Iterator[DataHub]:
        """
        DataHub 主入口（应用级单例）.

        所有依赖通过 Provider 注入，DataHub 不再使用 @cached_property.
        """
        # 创建 DataHub 并注入所有依赖
        hub = DataHub(
            data_root=data_root,
            sqlite_pool=sqlite_pool,
            file_lock=file_lock,
            sid_allocator=sid_allocator,
            freeze_manager=freeze_manager,
            instrument_store=instrument_store,
            securities=securities,
            metadata_query_service=metadata_query_service,
            market_query_service=market_query_service,
            fundamental_query_service=fundamental_query_service,
            capital_query_service=capital_query_service,
            macro_query_service=macro_query_service,
            features_query_service=features_query_service,
            factors_query_service=factors_query_service,
            calendar=calendar,
            adj_factor=adj_factor,
            bars=bars,
            universe=universe,
            index=index,
            ingestion_log=ingestion_log,
            quarantine=quarantine,
            sources=sources,
            sql_engine=sql_engine,
        )

        yield hub

        # 关闭 sqlite_pool
        sqlite_pool.close()
