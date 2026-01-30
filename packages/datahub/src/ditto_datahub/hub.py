"""DataHub - Unified data entry point for Ditto."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import polars as pl
from ditto_foundation import SQLitePool, logger
from ditto_foundation.concurrency import FileLockManager

from ditto_datahub.accessors.adj_factor_accessor import AdjFactorAccessor
from ditto_datahub.accessors.bars_accessor import AdjType, BarsAccessor, BarsQuery
from ditto_datahub.accessors.calendar_accessor import CalendarAccessor
from ditto_datahub.accessors.index_accessor import IndexAccessor
from ditto_datahub.accessors.ingestion_log_accessor import IngestionLogAccessor
from ditto_datahub.accessors.instrument_accessor import InstrumentsAccessor
from ditto_datahub.accessors.quarantine_accessor import QuarantineAccessor
from ditto_datahub.accessors.universe_accessor import UniverseAccessor
from ditto_datahub.domains.market import MarketService
from ditto_datahub.domains.metadata import MetadataService
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.errors import SidNotFoundError
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.source import DataSources

# 类型别名：标识符（支持 SID/src_code/symbol 混合）
type Identifier = str | int
type IdentifierList = list[Identifier]


@dataclass(frozen=True)
class BarsQuerySpec:
    """
    K 线查询参数（DataHub 便捷 API）。

    封装所有 K 线查询参数，支持混合标识符输入。

    Attributes:
        identifiers: 标识符列表（支持 SID/src_code/symbol 混合）。
        start: 开始日期 (YYYY-MM-DD)。
        end: 结束日期 (YYYY-MM-DD)。
        adj: 复权类型 (none/qfq/hfq)。
        asof: Point-in-time 查询日期。
        asset_class: 资产类别过滤。
        with_symbol: 是否添加 symbol 列。
        with_status: 是否添加状态列（仅股票）。
        raw: 是否跳过复权和状态增强。
        source: 数据源标识符（用于标识符解析）。

    Examples:
        >>> params = BarsQuerySpec(
        ...     identifiers=["000001.SZ", "万科A"],
        ...     start="2024-01-01",
        ...     end="2024-01-31",
        ... )
        >>> hub.get_bars(params)

    """

    identifiers: IdentifierList = field(default_factory=list)
    start: str | None = None
    end: str | None = None
    adj: Literal["none", "qfq", "hfq"] = "none"
    asof: str | None = None
    asset_class: Literal["stock", "etf", "index"] | None = None
    with_symbol: bool = False
    with_status: bool = False
    raw: bool = False
    source: str = "tushare"


@dataclass(frozen=True)
class SecuritiesQuerySpec:
    """
    证券查询参数（DataHub 便捷 API）。

    封装所有证券查询参数，支持混合标识符输入。

    Attributes:
        identifiers: 标识符列表（支持 SID/src_code/symbol 混合）。
        source: 数据源标识符。
        asset_class: 资产类别过滤。
        exchange: 交易所过滤。
        is_active: 是否活跃（None 表示全部）。
        asof: Point-in-time 查询日期。

    Examples:
        >>> params = SecuritiesQuerySpec(
        ...     identifiers=["000001.SZ", "万科A"],
        ...     asset_class="stock",
        ... )
        >>> hub.get_securities(params)

    """

    identifiers: IdentifierList = field(default_factory=list)
    source: str = "tushare"
    asset_class: str | None = None
    exchange: str | None = None
    is_active: bool | None = True
    asof: str | None = None


class DataHub:
    """
    Unified data entry point (Facade).

    All dependencies are injected through __init__ - no lazy loading.
    Component lifecycle is managed by the dishka container.

    Attribute layers:
    - Runtime Layer: sqlite_pool, file_lock, sid_allocator, freeze
    - Accessor Layer: securities, bars, calendar, universe, index, ingestion_log
    - Sources Layer: sources (external data sources: Tushare, Akshare)
    - SQL Engine: sql_engine

    Note: DQ checks are handled at the application layer (Port), not in DataHub.
    """

    def __init__(  # noqa: PLR0913
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
        calendar: CalendarAccessor,
        adj_factor: AdjFactorAccessor,
        bars: BarsAccessor,
        universe: UniverseAccessor,
        index: IndexAccessor,
        ingestion_log: IngestionLogAccessor,
        quarantine: QuarantineAccessor,
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
            freeze_manager: Freeze manager for data version tracking.
            instrument_store: Instrument store for identifier resolution.
            securities: Instruments accessor (with ingestion helpers).
            metadata_query_service: Metadata query service (unified query API).
            market_query_service: Market query service (unified market data API).
            calendar: Trading calendar accessor.
            adj_factor: Adjustment factor accessor.
            bars: OHLCV bars accessor.
            universe: 证券域访问器。
            index: Index data accessor.
            ingestion_log: Ingestion log accessor.
            quarantine: Quarantine accessor for DQ failed data.
            sources: External data sources.
            sql_engine: DuckDB SQL engine.

        """
        self.data_root = data_root
        self.sqlite_pool = sqlite_pool
        self.file_lock = file_lock
        self.sid_allocator = sid_allocator
        self.freeze = freeze_manager
        self._instrument_store = instrument_store
        self.securities = securities
        self.metadata = metadata_query_service
        self.market = market_query_service
        self.calendar = calendar
        self.adj_factor = adj_factor
        self.bars = bars
        self.universe = universe
        self.index = index
        self.ingestion_log = ingestion_log
        self.quarantine = quarantine
        self.sources = sources
        self.sql_engine = sql_engine

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
        result = self._instrument_store.resolve_sid(identifier, source, asof)
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
    # Identifier Resolution Facade (Task 2.3)
    # ========================================================================

    def resolve_identifiers(
        self,
        identifiers: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        批量解析标识符为 SID。

        Args:
            identifiers: 标识符列表（src_code 或 symbol）。
            source: 数据源标识符。
            asof: Point-in-time 查询日期。

        Returns:
            {identifier: sid} 映射字典（只包含找到的标识符）。

        """
        return self._instrument_store.resolve_sids_batch(identifiers, source, asof)

    def resolve_sids_from_inputs(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        symbols: list[str] | None = None,
        source: str = "tushare",
        asof: str | None = None,
    ) -> list[int]:
        """
        从多种输入类型解析 SID 列表。

        Args:
            sids: SID 列表（已知的 SID，无需转换）。
            src_codes: src_code 列表（需要转换）。
            symbols: symbol 列表（需要转换）。
            source: 数据源标识符。
            asof: Point-in-time 查询日期。

        Returns:
            去重后的 SID 列表（排序）。

        """
        resolved: set[int] = set()

        if sids:
            resolved.update(sids)

        if src_codes:
            mapping = self.resolve_identifiers(src_codes, source, asof)
            resolved.update(mapping.values())

        if symbols:
            for symbol in symbols:
                sid = self.resolve_sid(symbol, source, asof)
                if sid:
                    resolved.add(sid)

        return sorted(resolved)

    def get_symbol(self, sid: int) -> str | None:
        """获取 SID 对应的 symbol。"""
        return self.securities.get_symbol(sid)

    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """获取 SID 对应的 src_code。"""
        return self.securities.get_src_code(sid, source, asof)

    def get_sid_symbol_mapping(self, sids: list[int]) -> dict[int, str]:
        """批量获取 SID 到 symbol 的映射。"""
        result: dict[int, str] = {}
        for sid in sids:
            symbol = self.get_symbol(sid)
            if symbol:
                result[sid] = symbol
        return result

    # ========================================================================
    # Convenience API Methods (Task 2.4)
    # ========================================================================

    def get_bars(self, params: BarsQuerySpec) -> pl.DataFrame:
        """
        获取 K 线数据（便捷 API，支持混合标识符）。

        使用 BarsQuerySpec 对象封装查询参数，自动将标识符转换为 SID。

        Args:
            params: K 线查询参数对象。

        Returns:
            K 线数据 DataFrame。

        Examples:
            >>> # 使用参数对象
            >>> params = BarsQuerySpec(
            ...     identifiers=["000001.SZ", "万科A"],
            ...     start="2024-01-01",
            ...     end="2024-01-31",
            ... )
            >>> bars = hub.get_bars(params)

            >>> # 复权查询
            >>> params = BarsQuerySpec(
            ...     identifiers=["000001.SZ"],
            ...     start="2024-01-01",
            ...     adj="qfq",
            ...     with_symbol=True,
            ... )
            >>> bars = hub.get_bars(params)

        """
        # 分类标识符：SID、src_code、symbol
        sids: list[int] = []
        src_codes: list[str] = []
        symbols: list[str] = []

        for item in params.identifiers:
            if isinstance(item, int):
                sids.append(item)
            elif "." in str(item):
                # 字符串包含 '.'：判断为 src_code
                src_codes.append(str(item))
            else:
                # 字符串不包含 '.'：判断为 symbol
                symbols.append(str(item))

        # 解析 SID
        resolved_sids = self.resolve_sids_from_inputs(
            sids=sids if sids else None,
            src_codes=src_codes if src_codes else None,
            symbols=symbols if symbols else None,
            source=params.source,
            asof=params.asof,
        )

        if not resolved_sids:
            return pl.DataFrame()

        # 构造查询对象
        query = BarsQuery(
            sids=resolved_sids,
            start=params.start,
            end=params.end,
            adj=AdjType(params.adj),
            asof=params.asof,
            asset_class=params.asset_class,
            with_symbol=params.with_symbol,
            with_status=params.with_status,
            raw=params.raw,
        )

        return self.bars.get(query)

    def get_securities(self, params: SecuritiesQuerySpec) -> pl.DataFrame:
        """
        获取证券数据（便捷 API）。

        使用 SecuritiesQuerySpec 对象封装查询参数，自动将标识符转换为 SID。

        Args:
            params: 证券查询参数对象。

        Returns:
            证券数据 DataFrame。

        Examples:
            >>> # 使用参数对象
            >>> params = SecuritiesQuerySpec(
            ...     identifiers=["000001.SZ", "万科A"],
            ...     asset_class="stock",
            ... )
            >>> df = hub.get_securities(params)

            >>> # 查询全部（包括非活跃）
            >>> params = SecuritiesQuerySpec(
            ...     identifiers=["000001.SZ"],
            ...     is_active=None,
            ... )
            >>> df = hub.get_securities(params)

        """
        # 分类标识符
        sids: list[int] = []
        src_codes: list[str] = []
        symbols: list[str] = []

        for item in params.identifiers:
            if isinstance(item, int):
                sids.append(item)
            elif "." in str(item):
                # 字符串包含 '.'：判断为 src_code
                src_codes.append(str(item))
            else:
                # 字符串不包含 '.'：判断为 symbol
                symbols.append(str(item))

        # 解析 SID
        resolved_sids = self.resolve_sids_from_inputs(
            sids=sids if sids else None,
            src_codes=src_codes if src_codes else None,
            symbols=symbols if symbols else None,
            source=params.source,
            asof=params.asof,
        )

        return self.securities.get(
            sids=resolved_sids if resolved_sids else None,
            source=params.source,
            asset_class=params.asset_class,
            exchange=params.exchange,
            is_active=params.is_active,
            asof=params.asof,
        )

    def get_index_bars(
        self,
        sids: list[int] | None = None,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pl.DataFrame:
        """获取指数 K 线（便捷 API）。"""
        resolved_sids = self.resolve_sids_from_inputs(sids=sids, symbols=symbols)

        if not resolved_sids:
            return pl.DataFrame()

        return self.index.get_bars(
            sids=resolved_sids,
            start=start,
            end=end,
        )

    # ========================================================================
    # Resource Management
    # ========================================================================

    # Note: Resource lifecycle is managed by the dependency injection container.
    # The sqlite_pool is created and closed by the Provider/factory that created it.
    # DataHub is just a consumer of sqlite_pool and does not own its lifecycle.

    def __repr__(self) -> str:
        """Show DataHub info."""
        return f"DataHub(data_root='{self.data_root}')"
