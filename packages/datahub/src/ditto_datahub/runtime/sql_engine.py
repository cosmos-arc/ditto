"""SqlEngine - DuckDB SQL engine for DataHub."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
import polars as pl
from ditto_foundation import M, logger

if TYPE_CHECKING:
    from ditto_datahub.stores.calendar_store import CalendarStore
    from ditto_datahub.stores.security_store import SecurityStore

from ditto_datahub.runtime.pit_helper import PitHelper


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
            "index_weight",
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
            "stock_status",
            "ingestion_log",
            "ingestion_cursor",
        ]
    )

    def __init__(
        self,
        data_root: Path,
        security_store: SecurityStore,
        calendar_store: CalendarStore,
        enable_plan_cache: bool = True,
        plan_cache_size: int = 1000,
        slow_query_threshold: float = 1.0,
    ) -> None:
        """
        Initialize SqlEngine.

        Args:
            data_root: Data root directory path.
            security_store: Security store for metadata access.
            calendar_store: Calendar store for metadata access.
            enable_plan_cache: Enable query plan caching.
            plan_cache_size: Max size of query plan cache.
            slow_query_threshold: Slow query threshold in seconds.

        """
        self.data_root = data_root
        self.security_store = security_store
        self.calendar_store = calendar_store
        self.con = duckdb.connect(":memory:")
        self._sqlite_attached = False

        # 查询计划缓存
        self._enable_plan_cache = enable_plan_cache
        self._plan_cache: dict[str, Any] = {}
        self._plan_cache_size = plan_cache_size

        # 慢查询配置
        self._slow_query_threshold = slow_query_threshold

        self._setup()

        # PIT 辅助函数（类级别，无需实例化）
        self.pit_helper = PitHelper

        logger.debug(
            "SqlEngine initialized",
            event="sql_engine_init",
            data_root=str(data_root),
            enable_plan_cache=enable_plan_cache,
            plan_cache_size=plan_cache_size,
            slow_query_threshold=slow_query_threshold,
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
                    f"CREATE OR REPLACE VIEW {dataset} AS SELECT * FROM "  # nosec B608
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

    def _normalize_query(self, query: str) -> str:
        """
        Normalize query for caching.

        Remove extra whitespace and comments to generate cache key.

        Args:
            query: SQL query string.

        Returns:
            Normalized query string.

        """
        # Remove SQL comments
        query = re.sub(r"--.*?\n", " ", query)
        query = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)

        # Normalize whitespace
        query = re.sub(r"\s+", " ", query)
        query = query.strip()

        return query

    def _prepare_query(self, query: str) -> tuple[str, bool]:
        """
        Prepare query with caching support.

        Args:
            query: SQL query string.

        Returns:
            Tuple of (prepared_query, cache_hit).

        """
        normalized = self._normalize_query(query)

        if not self._enable_plan_cache:
            return normalized, False

        # Generate cache key using MD5 hash (非安全用途，仅用于缓存键生成)
        cache_key = hashlib.md5(normalized.encode()).hexdigest()  # nosec B324

        if cache_key in self._plan_cache:
            M.sql_query_plan_cache_hit.add(1)
            return self._plan_cache[cache_key], True

        M.sql_query_plan_cache_miss.add(1)

        # FIFO 淘汰：如果缓存已满，删除最旧的条目
        if len(self._plan_cache) >= self._plan_cache_size:
            # 简单的 FIFO：删除第一个条目
            # 在 Python 3.7+ 中 dict 保持插入顺序
            first_key = next(iter(self._plan_cache))
            del self._plan_cache[first_key]

        # 缓存准备好的查询
        self._plan_cache[cache_key] = normalized
        return normalized, False

    def _log_slow_query(self, query: str, duration: float) -> None:
        """
        Log slow query with metrics.

        Args:
            query: SQL query string.
            duration: Query execution duration in seconds.

        """
        # 记录慢查询指标（duration 已在 execute() 中记录，这里只记录慢查询计数）
        M.sql_slow_query_total.add(1)

        # 记录日志
        logger.warning(
            "Slow query detected",
            event="sql_slow_query",
            duration_seconds=duration,
            query_preview=query[:200] if len(query) > 200 else query,
        )

    def _needs_sqlite(self, query: str) -> bool:
        """
        Detect if query requires SQLite tables.

        Supports both:
        - SELECT * FROM security
        - SELECT * FROM meta.security

        Args:
            query: SQL query string.

        Returns:
            True if query references SQLite tables.

        """
        # Extract all table names (removing meta. prefix)
        table_pattern = r"\b(?:meta\.)?(\w+)\b"
        tables = re.findall(table_pattern, query.lower())

        # Check if any table is a SQLite table
        return any(table in self.SQLITE_TABLES for table in tables)

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
        start_time = time.monotonic()

        # 准备查询（带缓存）
        prepared_query, _cache_hit = self._prepare_query(query)

        # Attach SQLite if needed
        if self._needs_sqlite(prepared_query):
            self._attach_sqlite()
            # Prefix SQLite tables with meta. (if not already prefixed)
            for table in self.SQLITE_TABLES:
                # Only replace if not already prefixed with meta.
                # Negative lookahead: \btable\b not preceded by meta.
                pattern = r"\b(?<!meta\.)" + table + r"\b"
                prepared_query = re.sub(pattern, f"meta.{table}", prepared_query)

        # 使用参数化查询处理 $asof
        if asof is not None:
            # 验证 ISO 日期格式 (YYYY-MM-DD) 以防止 SQL 注入
            # 只允许安全字符：特定格式的数字和连字符
            if not isinstance(asof, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", asof):
                raise ValueError(
                    f"Invalid asof date format: {asof}. Expected YYYY-MM-DD format."
                )

            # 检查是否可以与 params 组合使用
            if isinstance(params, dict):
                raise ValueError(
                    "Cannot combine $asof parameter with dict params. "
                    "Use list params instead."
                )

            # 将 $asof 替换为 DuckDB 参数占位符
            # 策略：将 $asof 替换为新的参数占位符，避免与现有参数冲突
            # 例如：如果查询有 $1, $2，则 $asof 变为 $3

            # 计算查询中已有的参数数量
            existing_params = 0
            if params and isinstance(params, list):
                existing_params = len(params)

            # 新的参数编号
            new_param_num = existing_params + 1

            # 替换 $asof 为新的参数占位符
            prepared_query = prepared_query.replace("$asof", f"${new_param_num}")

            # 合并参数
            if params is None:
                params = [asof]
            elif isinstance(params, list):
                params = [*params, asof]

        # Execute query and convert to polars DataFrame
        if params:
            result = self.con.execute(prepared_query, params).pl()
        else:
            result = self.con.execute(prepared_query).pl()

        # 记录执行时间
        duration = time.monotonic() - start_time
        M.sql_query_duration.record(duration)

        # 慢查询检测
        if duration > self._slow_query_threshold:
            self._log_slow_query(query, duration)

        return result

    def pit_query(
        self,
        query: str,
        knowledge_date: str,
        date_column: str = "trade_date",
        params: list[Any] | dict[str, Any] | None = None,
    ) -> pl.DataFrame:
        """
        执行 PIT 查询（便捷方法）。

        自动为查询添加 PIT 过滤条件，确保只使用 knowledge_date 之前的数据。

        Args:
            query: SQL 查询（可使用 $asof 占位符）
            knowledge_date: 知识日期 (PIT 时间点)
            date_column: 日期列名，默认为 "trade_date"
            params: 查询参数

        Returns:
            查询结果

        Examples:
            >>> engine.pit_query(
            ...     "SELECT * FROM stock_daily WHERE sid = 1",
            ...     "2024-01-15"
            ... )
            # 自动添加: AND trade_date <= '2024-01-15'

            >>> engine.pit_query(
            ...     "SELECT * FROM stock_daily WHERE trade_date <= $asof",
            ...     "2024-01-15"
            ... )
            # $asof 会被替换为 '2024-01-15'

        """
        # 使用 PitHelper 添加 PIT 过滤条件
        pit_query = self.pit_helper.add_pit_filter(query, knowledge_date, date_column)

        # 执行查询
        return self.execute(pit_query, asof=knowledge_date, params=params)

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
