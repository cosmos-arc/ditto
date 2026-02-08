"""DataHub - Unified data entry point for Ditto."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import polars as pl
from ditto_foundation import SQLitePool, logger
from ditto_foundation.concurrency import FileLockManager

from ditto_datahub.domains.capital import CapitalService
from ditto_datahub.domains.factors import FactorService
from ditto_datahub.domains.features import FeatureService
from ditto_datahub.domains.fundamental import FundamentalService
from ditto_datahub.domains.macro import MacroService
from ditto_datahub.domains.market import (
    AdjType,
    MarketBarsQuery,
    MarketService,
)
from ditto_datahub.domains.metadata import MetadataService
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.errors import SidNotFoundError
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.ingestion import IngestionLogStore
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.sources.source import DataSources

# 类型别名：标识符（支持 SID/source_ticker/symbol 混合）
type Identifier = str | int
type IdentifierList = list[Identifier]


@dataclass(frozen=True)
class BarsQuerySpec:
    """
    K 线查询参数（DataHub 便捷 API）。

    封装所有 K 线查询参数，支持混合标识符输入。

    Attributes:
        identifiers: 标识符列表（支持 SID/source_ticker/symbol 混合）。
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
        identifiers: 标识符列表（支持 SID/source_ticker/symbol 混合）。
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
    - Runtime Layer: sqlite_pool, file_lock, instrument_id_allocator, freeze
    - Accessor Layer: securities, bars, calendar, universe, index, ingestion_log
    - Domain Services: metadata, market, fundamental, capital, macro, features, factors
    - Sources Layer: sources (external data sources: Tushare, Akshare)
    - SQL Engine: sql_engine

    Note: DQ checks are handled at the application layer (Port), not in DataHub.
    """

    def __init__(  # noqa: PLR0913
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
    ) -> None:
        """
        Initialize DataHub with all dependencies injected.

        所有组件由 dishka 容器创建并传入。
        移除了 Accessor 层，直接使用 Domain Services。

        Args:
            data_root: Data root directory path.
            sqlite_pool: SQLite connection pool.
            file_lock: File lock manager for concurrent write safety.
            instrument_id_allocator: Instrument ID allocator for new securities.
            freeze_manager: Freeze manager for data version tracking.
            instrument_store: Instrument store for identifier resolution.
            securities: Instruments accessor (with ingestion helpers).
            metadata_query_service: Metadata query service (unified query API).
            market_query_service: Market query service (unified market data API).
            fundamental_query_service: Fundamental query service.
            capital_query_service: Capital query service.
            macro_query_service: Macro query service.
            features_query_service: Features query service.
            factors_query_service: Factors query service.
            ingestion_log_store: Ingestion log store.
            sources: External data sources.
            sql_engine: DuckDB SQL engine.

        """
        self.data_root = data_root
        self.sqlite_pool = sqlite_pool
        self.file_lock = file_lock
        self.instrument_id_allocator = instrument_id_allocator
        self.freeze = freeze_manager
        self._instrument_store = instrument_store
        self.securities = metadata_query_service  # 向后兼容：securities -> metadata
        self.metadata = metadata_query_service
        self.market = market_query_service
        self.fundamental = fundamental_query_service
        self.capital = capital_query_service
        self.macro = macro_query_service
        self.features = features_query_service
        self.factors = factors_query_service
        self.sources = sources
        self.sql_engine = sql_engine

        # 向后兼容属性
        self._calendar = metadata_query_service
        self._universe = metadata_query_service
        self._index = market_query_service
        self._ingestion_log = ingestion_log_store

        logger.debug(
            "DataHub initialized",
            event="datahub_init",
            data_root=str(self.data_root),
        )

    @property
    def calendar(self) -> MetadataService:
        """向后兼容：calendar -> metadata."""
        return self._calendar

    @property
    def universe(self) -> MetadataService:
        """向后兼容：universe -> metadata."""
        return self._universe

    @property
    def index(self) -> MarketService:
        """向后兼容：index -> market."""
        return self._index

    @property
    def ingestion_log(self) -> IngestionLogStore:
        """向后兼容：ingestion_log -> ingestion_log_store."""
        return self._ingestion_log

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
            hub.sql("SELECT * FROM stock_daily WHERE instrument_id = 10001")

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

    def resolve_instrument_id(
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
        result = self._instrument_store.resolve_instrument_id(identifier, source, asof)
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
        # 直接使用 MetadataService.get_trading_days()
        return self.calendar.get_trading_days(start, end, only_open)

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
            identifiers: 标识符列表（source_ticker 或 symbol）。
            source: 数据源标识符。
            asof: Point-in-time 查询日期。

        Returns:
            {identifier: instrument_id} 映射字典（只包含找到的标识符）。

        """
        return self._instrument_store.resolve_instrument_ids_batch(
            identifiers, source, asof
        )

    def resolve_instrument_ids_from_inputs(
        self,
        instrument_ids: list[int] | None = None,
        source_tickers: list[str] | None = None,
        symbols: list[str] | None = None,
        source: str = "tushare",
        asof: str | None = None,
    ) -> list[int]:
        """
        从多种输入类型解析 SID 列表。

        Args:
            instrument_ids: SID 列表（已知的 SID，无需转换）。
            source_tickers: source_ticker 列表（需要转换）。
            symbols: symbol 列表（需要转换）。
            source: 数据源标识符。
            asof: Point-in-time 查询日期。

        Returns:
            去重后的 SID 列表（排序）。

        """
        resolved: set[int] = set()

        if instrument_ids:
            resolved.update(instrument_ids)

        if source_tickers:
            mapping = self.resolve_identifiers(source_tickers, source, asof)
            resolved.update(mapping.values())

        if symbols:
            for symbol in symbols:
                instrument_id = self.resolve_instrument_id(symbol, source, asof)
                if instrument_id:
                    resolved.add(instrument_id)

        return sorted(resolved)

    def get_symbol(self, instrument_id: int) -> str | None:
        """获取 SID 对应的 symbol。"""
        return self.securities.get_symbol(instrument_id)

    def get_source_ticker(
        self,
        instrument_id: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """获取 SID 对应的 source_ticker。"""
        return self.securities.get_source_ticker(instrument_id, source, asof)

    def get_instrument_id_symbol_mapping(
        self, instrument_ids: list[int]
    ) -> dict[int, str]:
        """批量获取 SID 到 symbol 的映射。"""
        result: dict[int, str] = {}
        for instrument_id in instrument_ids:
            symbol = self.get_symbol(instrument_id)
            if symbol:
                result[instrument_id] = symbol
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
        # 分类标识符：SID、source_ticker、symbol
        instrument_ids: list[int] = []
        source_tickers: list[str] = []
        symbols: list[str] = []

        for item in params.identifiers:
            if isinstance(item, int):
                instrument_ids.append(item)
            elif "." in str(item):
                # 字符串包含 '.'：判断为 source_ticker
                source_tickers.append(str(item))
            else:
                # 字符串不包含 '.'：判断为 symbol
                symbols.append(str(item))

        # 解析 SID
        resolved_sids = self.resolve_instrument_ids_from_inputs(
            instrument_ids=instrument_ids if instrument_ids else None,
            source_tickers=source_tickers if source_tickers else None,
            symbols=symbols if symbols else None,
            source=params.source,
            asof=params.asof,
        )

        if not resolved_sids:
            return pl.DataFrame()

        # 构造查询对象
        query = MarketBarsQuery(
            instrument_ids=resolved_sids,
            start=params.start,
            end=params.end,
            adj=AdjType(params.adj),
            asof=params.asof,
            asset_class=params.asset_class,
            with_symbol=params.with_symbol,
            with_status=params.with_status,
            raw=params.raw,
        )

        return self.market.get_bars(query)

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
        instrument_ids: list[int] = []
        source_tickers: list[str] = []
        symbols: list[str] = []

        for item in params.identifiers:
            if isinstance(item, int):
                instrument_ids.append(item)
            elif "." in str(item):
                # 字符串包含 '.'：判断为 source_ticker
                source_tickers.append(str(item))
            else:
                # 字符串不包含 '.'：判断为 symbol
                symbols.append(str(item))

        # 解析 SID
        resolved_sids = self.resolve_instrument_ids_from_inputs(
            instrument_ids=instrument_ids if instrument_ids else None,
            source_tickers=source_tickers if source_tickers else None,
            symbols=symbols if symbols else None,
            source=params.source,
            asof=params.asof,
        )

        return self.metadata.get_securities(
            instrument_ids=resolved_sids if resolved_sids else None,
            source=params.source,
            asset_class=params.asset_class,
            exchange=params.exchange,
            is_active=params.is_active,
            asof=params.asof,
        )

    def get_index_bars(
        self,
        instrument_ids: list[int] | None = None,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pl.DataFrame:
        """获取指数 K 线（便捷 API）。"""
        resolved_sids = self.resolve_instrument_ids_from_inputs(
            instrument_ids=instrument_ids, symbols=symbols
        )

        if not resolved_sids:
            return pl.DataFrame()

        # 使用 MarketService.get_bars()
        query = MarketBarsQuery(
            instrument_ids=resolved_sids,
            start=start,
            end=end,
        )
        return self.index.get_bars(query)

    def write_adj_factor(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: str = "error",
    ) -> dict[str, int]:
        """
        写入复权因子数据（转发到 MarketService）。

        Args:
            dataset: 数据集名称（"adj_factor" 或 "fund_adj"）.
            df: 要写入的数据 DataFrame.
            year: 年份.
            on_duplicate: 重复数据处理策略（"error", "skip", "overwrite"）.

        Returns:
            写入结果统计（{"rows": 行数, "files": 文件数}）.

        """
        return self.market.write_adj_factor(dataset, df, year, on_duplicate)

    def write_bars(
        self,
        df: pl.DataFrame,
        year: int,
        dataset: str = "stock_daily",
        on_duplicate: str = "error",
    ) -> dict[str, int]:
        """
        写入 K线数据（转发到 MarketService）。

        Args:
            df: 要写入的数据 DataFrame.
            year: 年份.
            dataset: 数据集名称（"stock_daily", "etf_daily", "index_daily"）.
            on_duplicate: 重复数据处理策略（"error", "skip", "overwrite"）.

        Returns:
            写入结果统计（{"rows": 行数, "files": 文件数}）.

        """
        return self.market.write_bars(df, year, dataset, on_duplicate)

    # ========================================================================
    # Resource Management
    # ========================================================================

    # Note: Resource lifecycle is managed by the dependency injection container.
    # The sqlite_pool is created and closed by the Provider/factory that created it.
    # DataHub is just a consumer of sqlite_pool and does not own its lifecycle.

    def __repr__(self) -> str:
        """Show DataHub info."""
        return f"DataHub(data_root='{self.data_root}')"
