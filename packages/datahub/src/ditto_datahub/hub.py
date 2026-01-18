"""DataHub - Unified data entry point for Ditto."""

from __future__ import annotations

import atexit
import types
from functools import cached_property
from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import SQLitePool, logger
from ditto_foundation.concurrency import FileLockManager
from ditto_foundation.config.paths import get_paths

from ditto_datahub.accessors.adj_factor import AdjFactorAccessor
from ditto_datahub.accessors.bars import BarsAccessor
from ditto_datahub.accessors.calendar import CalendarAccessor
from ditto_datahub.accessors.index import IndexAccessor
from ditto_datahub.accessors.security import SecuritiesAccessor
from ditto_datahub.accessors.universe import UniverseAccessor
from ditto_datahub.dq.engine import DQEngine
from ditto_datahub.errors import SidNotFoundError
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.provider import SourcesProvider
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_datahub.stores.stock_status_store import StockStatusStore  # B.3
from ditto_datahub.stores.universe_store import UniverseStore


class DataHub:
    """
    Unified data entry point (Facade).

    Uses @cached_property for lazy loading:
    - Components are only initialized on first access
    - Reduces startup time and allocates resources on demand

    Attribute layers:
    - Runtime Layer: sqlite_pool, file_lock, sid_allocator, dq_engine, freeze
    - Store Layer: security_store, calendar_store, bars_store, adj_factor_store,
      universe_store, index_weight_store, ingestion_log
    - Accessor Layer: securities, bars, calendar, universe, index
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
            self.data_root = get_paths().data_home
        else:
            self.data_root = Path(data_root)

        self._closed = False
        # 注册进程退出清理
        atexit.register(self._cleanup_on_exit)

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
        db_path = self.data_root / "meta" / "hub.sqlite"
        return SQLitePool(str(db_path))

    @cached_property
    def file_lock(self) -> FileLockManager:
        """File lock manager for concurrent write safety."""
        lock_dir = self.data_root / "locks"
        return FileLockManager(lock_dir)

    @cached_property
    def sid_allocator(self) -> SidAllocator:
        """SID allocator for new securities."""
        return SidAllocator(self.sqlite_pool)

    @cached_property
    def dq_engine(self) -> DQEngine:
        """New DQ engine with user override support."""
        # Use new method: load config with user override
        return DQEngine(data_root=self.data_root)

    @cached_property
    def freeze(self) -> FreezeManager:
        """Freeze manager for data version tracking."""
        return FreezeManager(data_root=str(self.data_root))

    # ========================================================================
    # Store Layer
    # ========================================================================

    @cached_property
    def security_store(self) -> SecurityStore:
        """Security data store."""
        return SecurityStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def calendar_store(self) -> CalendarStore:
        """Trading calendar store."""
        return CalendarStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def bars_store(self) -> BarsStore:
        """OHLCV bars store (Parquet)."""
        return BarsStore(data_root=self.data_root)

    @cached_property
    def adj_factor_store(self) -> AdjFactorStore:
        """Adjustment factor store (Parquet)."""
        return AdjFactorStore(data_root=self.data_root)

    @cached_property
    def stock_status_store(self) -> StockStatusStore:  # B.3
        """Stock status store (Parquet, year partitioned)."""
        return StockStatusStore(data_root=self.data_root)

    @cached_property
    def universe_store(self) -> UniverseStore:
        """Universe store for security universe data."""
        return UniverseStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def index_weight_store(self) -> IndexWeightStore:
        """Index weight store for index constituent data."""
        return IndexWeightStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def ingestion_log(self) -> IngestionLogStore:
        """Ingestion event log store (new system)."""
        return IngestionLogStore(SQLiteClient(self.sqlite_pool))

    @cached_property
    def quarantine_store(self) -> QuarantineStore:
        """Quarantine store for failed data."""
        quarantine_path = self.data_root / "quarantine.db"
        return QuarantineStore(quarantine_path)

    # ========================================================================
    # Accessor Layer
    # ========================================================================

    @cached_property
    def securities(self) -> SecuritiesAccessor:
        """Securities master data accessor."""
        return SecuritiesAccessor(
            security_store=self.security_store,
            sid_allocator=self.sid_allocator,
        )

    @cached_property
    def bars(self) -> BarsAccessor:
        """OHLCV bars accessor."""
        return BarsAccessor(
            bars_store=self.bars_store,
            security_store=self.security_store,
            adj_factor_store=self.adj_factor_store,
            stock_status_store=self.stock_status_store,  # B.3
            dq_engine=self.dq_engine,  # Use new DQEngine
            file_lock=self.file_lock,
            quarantine_store=self.quarantine_store,
        )

    @cached_property
    def adj_factor(self) -> AdjFactorAccessor:
        """Adjustment factor accessor."""
        return AdjFactorAccessor(
            adj_factor_store=self.adj_factor_store,
            file_lock=self.file_lock,
        )

    @cached_property
    def calendar(self) -> CalendarAccessor:
        """Trading calendar accessor."""
        return CalendarAccessor(
            calendar_store=self.calendar_store,
        )

    @cached_property
    def universe(self) -> UniverseAccessor:
        """Security universe accessor."""
        return UniverseAccessor(
            universe_store=self.universe_store,
            security_store=self.security_store,
            sid_allocator=self.sid_allocator,
        )

    @cached_property
    def index(self) -> IndexAccessor:
        """Index data accessor."""
        return IndexAccessor(
            bars_store=self.bars_store,
            index_weight_store=self.index_weight_store,
            security_store=self.security_store,
        )

    # ========================================================================
    # Sources Layer (External Data Sources)
    # ========================================================================

    @cached_property
    def sources(self) -> SourcesProvider:
        """External data sources accessor (Tushare, Akshare, etc.)."""
        return SourcesProvider()

    # ========================================================================
    # SQL Engine
    # ========================================================================

    @cached_property
    def sql_engine(self) -> SqlEngine:
        """DuckDB SQL engine."""
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

    def _cleanup_on_exit(self) -> None:
        """进程退出时清理（由 atexit 自动调用）."""
        if not self._closed:
            self.close()

    def close(self) -> None:
        """
        Close resources.

        Only closes resources that have been accessed (initialized).
        Unaccessed resources are never created and don't need closing.

        This method is idempotent - can be called multiple times safely.

        Closes in reverse order of initialization to avoid dependency issues:
        1. Stores with SQLite clients (calendar_store, security_store,
           universe_store, index_weight_store, ingestion_log)
        2. SQL engine (DuckDB)
        3. SQLite pool (connection manager)
        """
        if self._closed:
            return
        # Close stores that hold SQLiteClient references
        # These must be closed before sqlite_pool
        for store_name in (
            "calendar_store",
            "security_store",
            "universe_store",
            "index_weight_store",
            "ingestion_log",
            "quarantine_store",
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

        self._closed = True

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
