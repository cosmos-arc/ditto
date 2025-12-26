"""SqlEngine - DuckDB SQL engine for DataHub."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
import polars as pl
from ditto_foundation import logger

if TYPE_CHECKING:
    from ditto_datahub.stores.calendar_store import CalendarStore
    from ditto_datahub.stores.security_store import SecurityStore


class SqlEngine:
    """
    DuckDB SQL engine.

    Supports:
    - Parquet data views (stock_daily, etf_daily, index_daily, adj_factor)
    - SQLite metadata ATTACH on demand
    - Adjustment macros (qfq, qfq_now, market_hfq)
    - PIT queries (asof parameter)
    """

    # SQLite table names for auto-detection
    SQLITE_TABLES = frozenset(
        [
            "security",
            "security_mapping",
            "trading_calendar",
            "universe",
            "universe_constituent",
            "pipeline_run",
            "dq_issue",
        ]
    )

    # Allowed dataset names for view registration (security whitelist)
    ALLOWED_DATASETS = frozenset(
        [
            "stock_daily",
            "etf_daily",
            "index_daily",
            "index_weight",
            "adj_factor",
        ]
    )

    def __init__(
        self,
        data_root: Path,
        security_store: SecurityStore,
        calendar_store: CalendarStore,
    ) -> None:
        """
        Initialize SqlEngine.

        Args:
            data_root: Data root directory path.
            security_store: Security store for metadata access.
            calendar_store: Calendar store for metadata access.

        """
        self.data_root = data_root
        self.security_store = security_store
        self.calendar_store = calendar_store
        self.con = duckdb.connect(":memory:")
        self._sqlite_attached = False
        self._setup()

        logger.debug(
            "SqlEngine initialized",
            event="sql_engine_init",
            data_root=str(data_root),
        )

    def _setup(self) -> None:
        """Initialize DuckDB configuration."""
        self.con.execute("SET enable_progress_bar = false")
        self._register_views()
        self._register_macros()

    def _register_views(self) -> None:
        """Register Parquet datasets as DuckDB views."""
        # Use class-level whitelist for security validation
        for dataset in self.ALLOWED_DATASETS:
            parquet_path = self.data_root / dataset
            # Check if directory exists before creating view
            if parquet_path.exists():
                # Create view with glob pattern for year partitions
                # dataset is validated against ALLOWED_DATASETS whitelist
                view_sql = (
                    f"CREATE OR REPLACE VIEW {dataset} AS SELECT * FROM "
                    f'"{parquet_path}/*.parquet"'
                )
                self.con.execute(view_sql)

    def _register_macros(self) -> None:
        """Register adjustment macros."""
        # Only register macros if stock_daily view exists
        stock_daily_path = self.data_root / "stock_daily"
        adj_factor_path = self.data_root / "adj_factor"

        if stock_daily_path.exists() and adj_factor_path.exists():
            # Market HFQ view (后复权)
            self.con.execute("""
                CREATE OR REPLACE VIEW market_hfq AS
                SELECT
                    m.sid, m.trade_date,
                    m.open * COALESCE(f.adj_factor, 1.0) AS open,
                    m.high * COALESCE(f.adj_factor, 1.0) AS high,
                    m.low * COALESCE(f.adj_factor, 1.0) AS low,
                    m.close * COALESCE(f.adj_factor, 1.0) AS close,
                    m.volume, m.amount
                FROM stock_daily m
                LEFT JOIN adj_factor f
                    ON m.sid = f.sid AND m.trade_date = f.trade_date
            """)

            # QFQ macro (前复权 + PIT)
            self.con.execute("""
                CREATE OR REPLACE MACRO qfq(scan_date) AS TABLE
                WITH baseline AS (
                    SELECT
                        sid,
                        last(adj_factor ORDER BY trade_date) as base_factor
                    FROM adj_factor
                    WHERE trade_date <= cast(scan_date as DATE)
                    GROUP BY sid
                )
                SELECT
                    m.sid, m.trade_date,
                    m.open * COALESCE(f.adj_factor, 1.0) /
                        COALESCE(b.base_factor, 1.0) AS open,
                    m.high * COALESCE(f.adj_factor, 1.0) /
                        COALESCE(b.base_factor, 1.0) AS high,
                    m.low * COALESCE(f.adj_factor, 1.0) /
                        COALESCE(b.base_factor, 1.0) AS low,
                    m.close * COALESCE(f.adj_factor, 1.0) /
                        COALESCE(b.base_factor, 1.0) AS close,
                    m.volume, m.amount
                FROM stock_daily m
                LEFT JOIN adj_factor f
                    ON m.sid = f.sid AND m.trade_date = f.trade_date
                LEFT JOIN baseline b ON m.sid = b.sid
                WHERE m.trade_date <= cast(scan_date as DATE)
            """)

            # QFQ Now (当前前复权)
            self.con.execute("""
                CREATE OR REPLACE MACRO qfq_now() AS TABLE
                SELECT * FROM qfq(current_date())
            """)

    def _attach_sqlite(self) -> None:
        """Attach SQLite metadata database on demand."""
        if self._sqlite_attached:
            return

        sqlite_path = self.data_root / "meta" / "hub.sqlite"
        if not sqlite_path.exists():
            return

        self.con.execute(f"ATTACH '{sqlite_path}' AS meta")
        self._sqlite_attached = True

        logger.debug(
            "SQLite database attached",
            event="sql_engine_sqlite_attached",
            path=str(sqlite_path),
        )

    def _needs_sqlite(self, query: str) -> bool:
        """
        Detect if query requires SQLite tables.

        Args:
            query: SQL query string.

        Returns:
            True if query references SQLite tables.

        """
        query_lower = query.lower()
        for table in self.SQLITE_TABLES:
            if (
                f" {table}" in query_lower
                or f"from {table}" in query_lower
                or f"join {table}" in query_lower
            ):
                return True
        return False

    def execute(
        self,
        query: str,
        asof: str | None = None,
        params: list[Any] | dict[str, Any] | None = None,
    ) -> pl.DataFrame:
        """
        Execute SQL query.

        Automatically ATTACH SQLite if query references SQLite tables.

        Args:
            query: SQL query string.
            asof: Point-in-time date for PIT queries.
            params: Query parameters (list for positional $1, $2, etc.).

        Returns:
            Query result as polars DataFrame.

        """
        # Attach SQLite if needed
        if self._needs_sqlite(query):
            self._attach_sqlite()
            # Prefix SQLite tables with meta.
            for table in self.SQLITE_TABLES:
                # Replace table references with meta.table
                # Use word boundaries to avoid partial matches
                pattern = r"\b" + table + r"\b"
                query = re.sub(pattern, f"meta.{table}", query)

        # Replace $asof parameter
        if asof:
            query = query.replace("$asof", f"'{asof}'")

        # Execute query and convert to polars DataFrame
        if params:
            return self.con.execute(query, params).pl()
        return self.con.execute(query).pl()

    def refresh_views(self) -> None:
        """Re-register Parquet views (call after data updates)."""
        self._register_views()

        logger.debug(
            "Views refreshed",
            event="sql_engine_views_refreshed",
        )

    def close(self) -> None:
        """Close DuckDB connection."""
        try:
            self.con.close()
            logger.debug(
                "SqlEngine closed",
                event="sql_engine_close",
            )
        except Exception as e:
            logger.warning(
                "Failed to close SqlEngine",
                event="sql_engine_close_failed",
                error=str(e),
            )
