"""DataHub - Unified data entry point for Ditto."""

from __future__ import annotations

import atexit
import types
from pathlib import Path
from typing import Any

import polars as pl
from ditto_core.quality import QualityEngine
from ditto_foundation import SQLitePool, logger
from ditto_foundation.concurrency import FileLockManager

from ditto_datahub.accessors.adj_factor import AdjFactorAccessor
from ditto_datahub.accessors.bars import BarsAccessor
from ditto_datahub.accessors.calendar import CalendarAccessor
from ditto_datahub.accessors.index import IndexAccessor
from ditto_datahub.accessors.ingestion_log import IngestionLogAccessor
from ditto_datahub.accessors.security import SecuritiesAccessor
from ditto_datahub.accessors.universe import UniverseAccessor
from ditto_datahub.errors import SidNotFoundError
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.source import DataSources


class DataHub:
    """
    Unified data entry point (Facade).

    All dependencies are injected through __init__ - no lazy loading.
    Component lifecycle is managed by the dishka container.

    Attribute layers:
    - Runtime Layer: sqlite_pool, file_lock, sid_allocator, dq_engine, freeze
    - Accessor Layer: securities, bars, calendar, universe, index, ingestion_log
    - Sources Layer: sources (external data sources: Tushare, Akshare)
    - SQL Engine: sql_engine
    """

    def __init__(  # noqa: PLR0913
        self,
        data_root: Path,
        sqlite_pool: SQLitePool,
        file_lock: FileLockManager,
        sid_allocator: SidAllocator,
        dq_engine: QualityEngine,
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
    ) -> None:
        """
        Initialize DataHub with all dependencies injected.

        All components are created by the dishka container and passed in.
        This eliminates lazy loading and makes dependencies explicit.

        Args:
            data_root: Data root directory path.
            sqlite_pool: SQLite connection pool.
            file_lock: File lock manager for concurrent write safety.
            sid_allocator: SID allocator for new securities.
            dq_engine: Data quality engine.
            freeze_manager: Freeze manager for data version tracking.
            securities: Securities master data accessor.
            calendar: Trading calendar accessor.
            adj_factor: Adjustment factor accessor.
            bars: OHLCV bars accessor.
            universe: Security universe accessor.
            index: Index data accessor.
            ingestion_log: Ingestion log accessor.
            sources: External data sources.
            sql_engine: DuckDB SQL engine.

        """
        self.data_root = data_root
        self.sqlite_pool = sqlite_pool
        self.file_lock = file_lock
        self.sid_allocator = sid_allocator
        self.dq_engine = dq_engine
        self.freeze = freeze_manager
        self.securities = securities
        self.calendar = calendar
        self.adj_factor = adj_factor
        self.bars = bars
        self.universe = universe
        self.index = index
        self.ingestion_log = ingestion_log
        self.sources = sources
        self.sql_engine = sql_engine

        self._closed = False
        # 注册进程退出清理
        atexit.register(self._cleanup_on_exit)

        logger.debug(
            "DataHub initialized",
            event="datahub_init",
            data_root=str(self.data_root),
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
        result = self.securities.resolve_sid(identifier, source, asof)
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

        This method is idempotent - can be called multiple times safely.

        Note: Most resources are managed by the dishka container.
        This method mainly ensures sqlite_pool is closed when used
        outside the container (backward compatibility).
        """
        if self._closed:
            return

        # Close SQLite pool if it hasn't been closed by container
        if hasattr(self, "sqlite_pool"):
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
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: types.TracebackType | None,
    ) -> None:
        """Auto-close on exit."""
        self.close()

    def __repr__(self) -> str:
        """Show DataHub info."""
        return f"DataHub(data_root='{self.data_root}')"
