"""DataHub - Unified data entry point for Ditto."""

from __future__ import annotations

import types
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from ditto_foundation import logger

from ditto_datahub.errors import SidNotFoundError

if TYPE_CHECKING:
    from ditto_datahub.repositories.bars import BarsRepository
    from ditto_datahub.repositories.calendar import CalendarRepository
    from ditto_datahub.repositories.index import IndexRepository
    from ditto_datahub.repositories.security import SecurityRepository
    from ditto_datahub.repositories.universe import UniverseRepository
    from ditto_datahub.runtime.dq_checker import DQChecker
    from ditto_datahub.runtime.file_lock import FileLockManager
    from ditto_datahub.runtime.freeze_manager import FreezeManager
    from ditto_datahub.runtime.sid_allocator import SidAllocator
    from ditto_datahub.runtime.sql_engine import SqlEngine
    from ditto_datahub.runtime.sqlite_pool import SQLitePool
    from ditto_datahub.sources.accessor import SourcesAccessor
    from ditto_datahub.stores.adj_factor_store import AdjFactorStore
    from ditto_datahub.stores.bars_store import BarsStore
    from ditto_datahub.stores.calendar_store import CalendarStore
    from ditto_datahub.stores.index_weight_store import IndexWeightStore
    from ditto_datahub.stores.ingestion_metadata_store import IngestionMetadataStore
    from ditto_datahub.stores.pipeline_store import PipelineStore
    from ditto_datahub.stores.security_store import SecurityStore
    from ditto_datahub.stores.universe_store import UniverseStore


class DataHub:
    """
    Unified data entry point (Facade).

    Uses @cached_property for lazy loading:
    - Components are only initialized on first access
    - Reduces startup time and allocates resources on demand

    Attribute layers:
    - Runtime Layer: sqlite_pool, file_lock, sid_allocator, dq_checker, freeze
    - Store Layer: security_store, calendar_store, bars_store, adj_factor_store,
      pipeline_store, universe_store, index_weight_store
    - Repository Layer: securities, bars, calendar, universe, index
    - Sources Layer: sources (external data sources: Tushare, Akshare)
    - SQL Engine: sql_engine
    """

    def __init__(self, data_root: str | Path | None = None) -> None:
        r"""
        Initialize DataHub.

        Args:
            data_root: Data root directory path.
                If None, uses XDG Base Directory spec
                (D:\\data\\ditto\\data on Windows).

        """
        if data_root is None:
            from ditto_foundation.config.paths import get_paths

            self.data_root = get_paths().data_home
        else:
            self.data_root = Path(data_root)

        logger.debug(
            "DataHub initialized",
            event="datahub_init",
            data_root=str(self.data_root),
        )

    # ========================================================================
    # Runtime Layer
    # ========================================================================

    @cached_property
    def sqlite_pool(self) -> SQLitePool:
        """SQLite connection pool."""
        from ditto_datahub.runtime.sqlite_pool import SQLitePool

        db_path = self.data_root / "meta" / "hub.sqlite"
        return SQLitePool(str(db_path))

    @cached_property
    def file_lock(self) -> FileLockManager:
        """File lock manager for concurrent write safety."""
        from ditto_datahub.runtime.file_lock import FileLockManager

        lock_dir = self.data_root / "locks"
        return FileLockManager(lock_dir)

    @cached_property
    def sid_allocator(self) -> SidAllocator:
        """SID allocator for new securities."""
        from ditto_datahub.runtime.sid_allocator import SidAllocator

        return SidAllocator(self.sqlite_pool)

    @cached_property
    def dq_checker(self) -> DQChecker:
        """Data quality checker."""
        from ditto_datahub.runtime.dq_checker import DQChecker

        return DQChecker()

    @cached_property
    def freeze(self) -> FreezeManager:
        """Freeze manager for data version tracking."""
        from ditto_datahub.runtime.freeze_manager import FreezeManager

        return FreezeManager(data_root=str(self.data_root))

    # ========================================================================
    # Store Layer
    # ========================================================================

    @cached_property
    def security_store(self) -> SecurityStore:
        """Security data store."""
        from ditto_datahub.stores.security_store import SecurityStore
        from ditto_datahub.stores.sqlite_client import SQLiteClient

        return SecurityStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def calendar_store(self) -> CalendarStore:
        """Trading calendar store."""
        from ditto_datahub.stores.calendar_store import CalendarStore
        from ditto_datahub.stores.sqlite_client import SQLiteClient

        return CalendarStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def bars_store(self) -> BarsStore:
        """OHLCV bars store (Parquet)."""
        from ditto_datahub.stores.bars_store import BarsStore

        return BarsStore(data_root=self.data_root)

    @cached_property
    def adj_factor_store(self) -> AdjFactorStore:
        """Adjustment factor store (Parquet)."""
        from ditto_datahub.stores.adj_factor_store import AdjFactorStore

        return AdjFactorStore(data_root=self.data_root)

    @cached_property
    def pipeline_store(self) -> PipelineStore:
        """Pipeline run store."""
        from ditto_datahub.stores.pipeline_store import PipelineStore
        from ditto_datahub.stores.sqlite_client import SQLiteClient

        return PipelineStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def universe_store(self) -> UniverseStore:
        """Universe store for security universe data."""
        from ditto_datahub.stores.sqlite_client import SQLiteClient
        from ditto_datahub.stores.universe_store import UniverseStore

        return UniverseStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def index_weight_store(self) -> IndexWeightStore:
        """Index weight store for index constituent data."""
        from ditto_datahub.stores.index_weight_store import IndexWeightStore
        from ditto_datahub.stores.sqlite_client import SQLiteClient

        return IndexWeightStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def ingestion_metadata_store(self) -> IngestionMetadataStore:
        """Ingestion metadata store for incremental data fetching."""
        from ditto_datahub.stores.ingestion_metadata_store import IngestionMetadataStore
        from ditto_datahub.stores.sqlite_client import SQLiteClient

        return IngestionMetadataStore(SQLiteClient(self.sqlite_pool))

    # ========================================================================
    # Repository Layer
    # ========================================================================

    @cached_property
    def securities(self) -> SecurityRepository:
        """Securities master data repository."""
        from ditto_datahub.repositories.security import SecurityRepository

        return SecurityRepository(
            security_store=self.security_store,
            sid_allocator=self.sid_allocator,
        )

    @cached_property
    def bars(self) -> BarsRepository:
        """OHLCV bars repository."""
        from ditto_datahub.repositories.bars import BarsRepository

        return BarsRepository(
            bars_store=self.bars_store,
            security_store=self.security_store,
            adj_factor_store=self.adj_factor_store,
            dq_checker=self.dq_checker,
            file_lock=self.file_lock,
        )

    @cached_property
    def calendar(self) -> CalendarRepository:
        """Trading calendar repository."""
        from ditto_datahub.repositories.calendar import CalendarRepository

        return CalendarRepository(
            calendar_store=self.calendar_store,
        )

    @cached_property
    def universe(self) -> UniverseRepository:
        """Security universe repository."""
        from ditto_datahub.repositories.universe import UniverseRepository

        return UniverseRepository(
            universe_store=self.universe_store,
            sid_allocator=self.sid_allocator,
        )

    @cached_property
    def index(self) -> IndexRepository:
        """Index data repository."""
        from ditto_datahub.repositories.index import IndexRepository

        return IndexRepository(
            bars_store=self.bars_store,
            index_weight_store=self.index_weight_store,
            security_store=self.security_store,
        )

    # ========================================================================
    # Sources Layer (External Data Sources)
    # ========================================================================

    @cached_property
    def sources(self) -> SourcesAccessor:
        """External data sources accessor (Tushare, Akshare, etc.)."""
        from ditto_datahub.sources.accessor import SourcesAccessor

        return SourcesAccessor()

    # ========================================================================
    # SQL Engine
    # ========================================================================

    @cached_property
    def sql_engine(self) -> SqlEngine:
        """DuckDB SQL engine."""
        from ditto_datahub.runtime.sql_engine import SqlEngine

        return SqlEngine(
            data_root=self.data_root,
            security_store=self.security_store,
            calendar_store=self.calendar_store,
        )

    # ========================================================================
    # Convenience Methods
    # ========================================================================

    def sql(
        self,
        query: str,
        asof: str | None = None,
        params: list[Any] | dict[str, Any] | None = None,
    ) -> pl.DataFrame:
        """
        Execute SQL query.

        Automatically ATTACH SQLite if query references SQLite tables.

        Examples:
            # Basic query
            hub.sql("SELECT * FROM stock_daily WHERE sid = 10001")

            # PIT query
            hub.sql(
                "SELECT * FROM stock_daily WHERE trade_date <= $asof",
                asof="2024-06-30",
            )

        Args:
            query: SQL query string.
            asof: Point-in-time date for PIT queries.
            params: Query parameters.

        Returns:
            Query result as polars DataFrame.

        """
        return self.sql_engine.execute(query, asof=asof, params=params)

    def resolve_sid(
        self,
        identifier: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int:
        """
        Resolve identifier to SID (supports PIT).

        Args:
            identifier: Source code or symbol.
            source: Data source identifier.
            asof: Point-in-time query date.

        Returns:
            SID.

        Raises:
            SidNotFoundError: If identifier cannot be resolved.

        """
        result = self.security_store.resolve_sid(identifier, source, asof)
        if result is None:
            raise SidNotFoundError(
                message=f"Identifier '{identifier}' not found in source '{source}'",
                identifier=identifier,
                source=source,
            )
        return result

    def refresh_sql_views(self) -> None:
        """
        Refresh SQL engine views (call after data updates).

        This should be called after writing new data to refresh
        the DuckDB views that reference Parquet files.
        """
        if "sql_engine" in self.__dict__:
            self.sql_engine.refresh_views()

    def get_trading_days(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> list[str]:
        """
        Get trading days list (convenience method).

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            only_open: Only return trading days (default True).

        Returns:
            List of trading dates.

        """
        df = self.calendar.get(start, end, only_open)
        return df["trade_date"].to_list()

    def is_trading_day(self, date: str) -> bool:
        """
        Check if date is a trading day (convenience method).

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            True if trading day.

        """
        return self.calendar.is_trading_day(date)

    # ========================================================================
    # Resource Management
    # ========================================================================

    def close(self) -> None:
        """
        Close resources.

        Only closes resources that have been accessed (initialized).
        Unaccessed resources are never created and don't need closing.

        Closes in reverse order of initialization to avoid dependency issues:
        1. Stores with SQLite clients (pipeline_store, calendar_store, security_store,
           universe_store, index_weight_store)
        2. SQL engine (DuckDB)
        3. SQLite pool (connection manager)
        """
        # Close stores that hold SQLiteClient references
        # These must be closed before sqlite_pool
        for store_name in (
            "pipeline_store",
            "calendar_store",
            "security_store",
            "universe_store",
            "index_weight_store",
        ):
            if store_name in self.__dict__:
                store = getattr(self, store_name)
                if hasattr(store, "close"):
                    store.close()

        # Close SQL engine
        if "sql_engine" in self.__dict__:
            self.sql_engine.close()

        # Close SQLite pool
        if "sqlite_pool" in self.__dict__:
            self.sqlite_pool.close()

        logger.debug(
            "DataHub closed",
            event="datahub_close",
        )

    def __enter__(self) -> DataHub:
        """Support with statement."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Auto-close on exit."""
        self.close()

    def __repr__(self) -> str:
        """Show initialized components."""
        initialized = [
            k for k in self.__dict__ if not k.startswith("_") and k != "data_root"
        ]
        return f"DataHub(data_root='{self.data_root}', initialized={initialized})"
