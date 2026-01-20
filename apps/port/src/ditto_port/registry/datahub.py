"""
DataHub 组件注册.

Root 注入模式：在 Provider 中集中注册所有 DataHub 组件。
所有依赖通过 Provider 管理，DataHub 不再使用 @cached_property.
"""

from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub import DataHub
from ditto_datahub.accessors.adj_factor import AdjFactorAccessor
from ditto_datahub.accessors.bars import BarsAccessor
from ditto_datahub.accessors.calendar import CalendarAccessor
from ditto_datahub.accessors.index import IndexAccessor
from ditto_datahub.accessors.ingestion_log import IngestionLogAccessor
from ditto_datahub.accessors.security import SecuritiesAccessor
from ditto_datahub.accessors.universe import UniverseAccessor
from ditto_datahub.dq.engine import DQEngine
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tushare.tushare_source import TushareSource
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore
from ditto_datahub.stores.universe_store import UniverseStore
from ditto_foundation import SQLitePool
from ditto_foundation.concurrency import FileLockManager
from ditto_foundation.config.paths import get_paths

__all__ = ["DataHubProvider"]


class DataHubProvider(Provider):
    """DataHub 组件 Provider."""

    scope = Scope.APP

    @provide
    def data_root(self) -> Path:
        """数据根目录."""
        return get_paths().data_home

    # ========================================================================
    # Runtime Layer
    # ========================================================================

    @provide
    def sqlite_pool(self, data_root: Path) -> Iterator[SQLitePool]:
        """SQLite 连接池（应用级单例）."""
        db_path = data_root / "meta" / "hub.sqlite"
        pool = SQLitePool(str(db_path))
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
    def dq_engine(self, data_root: Path) -> DQEngine:
        """数据质量引擎."""
        return DQEngine(data_root=data_root)

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
    def security_store(self, sqlite_client: SQLiteClient) -> SecurityStore:
        """证券数据存储."""
        return SecurityStore(sqlite_client)

    @provide
    def calendar_store(self, sqlite_client: SQLiteClient) -> CalendarStore:
        """交易日历存储."""
        return CalendarStore(sqlite_client)

    @provide
    def bars_store(self, data_root: Path) -> BarsStore:
        """OHLCV 数据存储."""
        return BarsStore(data_root=data_root)

    @provide
    def adj_factor_store(self, data_root: Path) -> AdjFactorStore:
        """复权因子存储."""
        return AdjFactorStore(data_root=data_root)

    @provide
    def stock_status_store(self, data_root: Path) -> StockStatusStore:
        """股票状态存储."""
        return StockStatusStore(data_root=data_root)

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
    def quarantine_store(self, data_root: Path) -> QuarantineStore:
        """隔离区存储."""
        quarantine_path = data_root / "quarantine.db"
        return QuarantineStore(quarantine_path)

    # ========================================================================
    # Accessor Layer
    # ========================================================================

    @provide
    def securities(
        self,
        security_store: SecurityStore,
        sid_allocator: SidAllocator,
    ) -> SecuritiesAccessor:
        """证券数据访问器."""
        return SecuritiesAccessor(
            security_store=security_store,
            sid_allocator=sid_allocator,
        )

    @provide
    def calendar(self, calendar_store: CalendarStore) -> CalendarAccessor:
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
        security_store: SecurityStore,
        adj_factor_store: AdjFactorStore,
        stock_status_store: StockStatusStore,
        dq_engine: DQEngine,
        file_lock: FileLockManager,
        quarantine_store: QuarantineStore,
    ) -> BarsAccessor:
        """OHLCV 数据访问器."""
        return BarsAccessor(
            bars_store=bars_store,
            security_store=security_store,
            adj_factor_store=adj_factor_store,
            stock_status_store=stock_status_store,
            dq_engine=dq_engine,
            file_lock=file_lock,
            quarantine_store=quarantine_store,
        )

    @provide
    def universe(
        self,
        universe_store: UniverseStore,
        security_store: SecurityStore,
        sid_allocator: SidAllocator,
    ) -> UniverseAccessor:
        """证券集合访问器."""
        return UniverseAccessor(
            universe_store=universe_store,
            security_store=security_store,
            sid_allocator=sid_allocator,
        )

    @provide
    def index(
        self,
        bars_store: BarsStore,
        index_weight_store: IndexWeightStore,
        security_store: SecurityStore,
    ) -> IndexAccessor:
        """指数数据访问器."""
        return IndexAccessor(
            bars_store=bars_store,
            index_weight_store=index_weight_store,
            security_store=security_store,
        )

    @provide
    def ingestion_log(
        self,
        ingestion_log_store: IngestionLogStore,
    ) -> IngestionLogAccessor:
        """摄取日志访问器."""
        return IngestionLogAccessor(ingestion_log_store=ingestion_log_store)

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
        security_store: SecurityStore,
        calendar_store: CalendarStore,
    ) -> SqlEngine:
        """DuckDB SQL 引擎."""
        return SqlEngine(
            data_root=data_root,
            security_store=security_store,
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
        dq_engine: DQEngine,
        freeze_manager: FreezeManager,
        securities: SecuritiesAccessor,
        calendar: CalendarAccessor,
        adj_factor: AdjFactorAccessor,
        bars: BarsAccessor,
        universe: UniverseAccessor,
        index: IndexAccessor,
        ingestion_log: IngestionLogAccessor,
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
            dq_engine=dq_engine,
            freeze_manager=freeze_manager,
            securities=securities,
            calendar=calendar,
            adj_factor=adj_factor,
            bars=bars,
            universe=universe,
            index=index,
            ingestion_log=ingestion_log,
            sources=sources,
            sql_engine=sql_engine,
        )

        yield hub

        # 关闭 sqlite_pool
        sqlite_pool.close()
