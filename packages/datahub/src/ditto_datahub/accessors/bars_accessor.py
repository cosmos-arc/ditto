"""Bars Accessor for market data access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Literal

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.concurrency import FileLockManager

from ditto_datahub.accessors.internal.adjustment import apply_hfq_adj, apply_qfq_adj
from ditto_datahub.accessors.internal.enrichment import enrich_with_status
from ditto_datahub.models import AssetSidRange, OnDuplicate, WriteResult
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.stock_status_store import StockStatusStore  # B.3


class AdjType(Enum):
    """Adjustment type for price data."""

    NONE = "none"  # No adjustment
    QFQ = "qfq"  # Forward adjustment (前复权)
    HFQ = "hfq"  # Backward adjustment (后复权)


@dataclass(frozen=True)
class BarsQuery:
    """
    行情查询参数。

    用于封装 BarsAccessor.get() 方法的所有参数，提高可读性和可维护性。

    Attributes:
        sids: 按 SID 列表过滤。
        src_codes: 按源代码列表过滤。
        symbols: 按代码列表过滤。
        start: 开始日期 (YYYY-MM-DD)。
        end: 结束日期 (YYYY-MM-DD)。
        adj: 复权类型。
        asof: 时间点查询日期 (PIT-safe)。
            - 用于标识符解析：获取截至该日期有效的 SID。
            - 用于调整因子：仅使用 knowledge_date <= asof 的因子。
            - 如果为 None，使用当前数据（非 PIT-safe）。
        asset_class: 资产类别过滤。
        with_symbol: 是否在结果中添加 symbol 列。
        with_status: 是否添加股票状态列（仅对股票数据有效）。
        market_wide: 全市场查询模式。为 True 时获取所有活跃证券，不限制 SID 范围。
        raw: 是否跳过复权和状态增强。为 True 时返回原始数据，不应用复权和状态增强。

    Examples:
        >>> query = BarsQuery(sids=[1, 2, 3], start="2024-01-01", end="2024-01-31")
        >>> repo.get(query)

    """

    sids: list[int] | None = None
    src_codes: list[str] | None = None
    symbols: list[str] | None = None
    start: str | None = None
    end: str | None = None
    adj: AdjType = AdjType.NONE
    asof: str | None = None
    asset_class: Literal["stock", "etf", "index"] | None = None
    with_symbol: bool = False
    with_status: bool = False
    market_wide: bool = False
    raw: bool = False


@dataclass(frozen=True, slots=True)
class _ResolvedQuery:
    """
    解析后的查询参数。

    用于存储解析和验证后的查询参数，传递给数据加载和处理方法。
    这是内部 API（前导下划线），仅供 BarsAccessor 内部使用。

    Attributes:
        sids: 解析后的 SID 列表（非空）。
        start: 开始日期（解析为 date 对象）。
        end: 结束日期（解析为 date 对象）。
        asof: 时间点查询日期（解析为 date 对象，PIT-safe）。
        asset_class: 资产类别（如 "stock", "etf", "index"）。

    Examples:
        >>> from datetime import date
        >>> resolved = _ResolvedQuery(
        ...     sids=[1, 2, 3],
        ...     start=date(2024, 1, 1),
        ...     end=date(2024, 1, 31),
        ...     asof=None,
        ...     asset_class="stock",
        ... )

    """

    sids: list[int]
    start: date | None
    end: date | None
    asof: date | None
    asset_class: str | None


class BarsAccessor:
    """
    Market data accessor for OHLCV bars.

    Provides domain-level interface for bars data operations,
    coordinating multiple stores for data access, adjustment,
    and identifier resolution.

    Note: DQ checks are handled at the application layer (Port), not in DataHub.
    """

    def __init__(
        self,
        bars_store: BarsStore,
        adj_factor_store: AdjFactorStore,
        security_store: SecurityStore,
        stock_status_store: StockStatusStore,  # B.3
        file_lock: FileLockManager,
    ) -> None:
        """
        Initialize BarsAccessor.

        Args:
            bars_store: Bars data store.
            adj_factor_store: Adjustment factor store.
            security_store: Security store for identifier resolution.
            stock_status_store: Stock status store (B.3).
            file_lock: File lock manager for concurrent writes.

        """
        self._bars_store = bars_store
        self._adj_factor_store = adj_factor_store
        self._security_store = security_store
        self._stock_status_store = stock_status_store  # B.3
        self._file_lock = file_lock

    @traced("accessor.bars.get")
    def get(self, query: BarsQuery) -> pl.DataFrame:
        """
        获取行情数据（使用查询对象）。

        Args:
            query: BarsQuery 查询对象，包含所有查询参数。

        Returns:
            行情数据 DataFrame。

        Raises:
            ValueError: 如果无法解析出有效的 SID。

        Examples:
            >>> query = BarsQuery(sids=[1, 2, 3], start="2024-01-01", end="2024-01-31")
            >>> repo.get(query)

        """
        logger.debug(
            "Fetching bars data",
            event="bars_get_start",
            start=query.start,
            end=query.end,
            adj=query.adj.value,
            with_status=query.with_status,
            market_wide=query.market_wide,
        )

        # 1. 参数验证和解析
        try:
            resolved = self._resolve_query(query)
        except ValueError as e:
            # 如果无法解析出有效的 SID，返回空 DataFrame
            # 其他 ValueError（如混合资产类别）应该继续抛出
            if "无法解析出有效的 SID" in str(e):
                return pl.DataFrame()
            raise

        # 2. 加载核心数据
        df = self._load_bars_core(resolved)

        if df.is_empty():
            return pl.DataFrame()

        # 3. 应用复权（如果需要且不是 raw 模式）
        if not query.raw and query.adj != AdjType.NONE:
            df = self._apply_adjustment(df, query.adj, resolved)

        # 4. 增强 data
        # 4.1 添加 symbol 列（如果需要）
        if query.with_symbol:
            df = self._security_store.enrich_with_symbol(df)

        # 4.2 添加状态列（如果需要且不是 raw 模式）
        if query.with_status and not query.raw and resolved.asset_class == "stock":
            df = self._enrich_with_status(
                df, resolved.sids, resolved.start, resolved.end
            )

        logger.debug(
            "Bars data fetched",
            event="bars_get_complete",
            row_count=len(df),
            adj=query.adj.value,
        )

        # 记录指标
        M.data_records.add(
            len(df), {"dataset": "bars", "operation": "get", "adj": query.adj.value}
        )

        return df

    def get_single(
        self,
        identifier: str,
        start: str,
        end: str,
        source: str = "tushare",
        adj: AdjType = AdjType.NONE,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Get bars data for a single security.

        Args:
            identifier: Source code or symbol.
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            source: Data source identifier.
            adj: Adjustment type.
            asof: Point-in-time date (for PIT-safe identifier resolution and query).

        Returns:
            Bars data DataFrame.

        """
        # Resolve identifier (try src_code first, then symbol)
        # Note: asof is passed here for PIT-safe identifier resolution
        sid = self._security_store.resolve_sid(identifier, source, asof)
        if not sid:
            # Try as symbol
            sids = self._security_store.resolve_by_symbol(identifier, source)
            if not sids:
                return pl.DataFrame()

            # Warn if multiple SIDs match the same symbol
            if len(sids) > 1:
                logger.warning(
                    "Multiple SIDs found for symbol, using first match",
                    event="symbol_multiple_matches",
                    symbol=identifier,
                    sids=sids,
                    selected_sid=sids[0],
                    match_count=len(sids),
                )

            sid = sids[0]

        # Get data (使用 BarsQuery)
        return self.get(
            query=BarsQuery(
                sids=[sid],
                start=start,
                end=end,
                adj=adj,
                asof=asof,
                with_symbol=True,
            )
        )

    @traced("accessor.bars.write")
    def write(
        self,
        df: pl.DataFrame,
        year: int,
        dataset: str = "stock_daily",
        source: str = "tushare",
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        Write bars data.

        Note: DQ checks should be performed at the application layer (Port)
        before calling this method. This method only handles data storage.

        Args:
            df: Bars data DataFrame.
            year: Year partition for storage.
            dataset: Dataset name.
            source: Data source identifier.
            on_duplicate: Strategy for handling duplicate data.

        Returns:
            Write result with file path and checksum.

        """
        logger.info(
            "Writing bars data",
            event="bars_write_start",
            dataset=dataset,
            year=year,
            row_count=len(df),
        )

        # Use file lock for concurrent safety
        lock_name = f"bars_write_{dataset}_{year}"
        with self._file_lock.acquire(lock_name, timeout=60.0):
            # Write data
            result = self._bars_store.write(
                dataset, df, year, on_duplicate=on_duplicate
            )
            file_path = result.file_path
            checksum = result.checksum

            # Get total rows after write
            total_rows = len(
                self._bars_store.read(
                    dataset=dataset,
                    sids=None,
                    start_date=f"{year}-01-01",
                    end_date=f"{year}-12-31",
                )
            )

            logger.info(
                "Bars data written",
                event="bars_write_complete",
                dataset=dataset,
                year=year,
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=total_rows,
            )

            # Record metrics
            M.data_records.add(len(df), {"dataset": "bars", "operation": "write"})

            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=total_rows,
                blocked=False,
            )

    def _resolve_query(self, query: BarsQuery) -> _ResolvedQuery:
        """
        解析和验证查询参数。

        Args:
            query: BarsQuery 查询对象。

        Returns:
            解析后的查询参数（_ResolvedQuery）。

        Raises:
            ValueError: 如果无法解析出有效的 SID。

        """
        # 1. 解析 SID 列表
        # 全市场模式：获取所有活跃 SID
        if query.market_wide:
            resolved_sids = self._security_store.list_sids(
                asset_class=query.asset_class,
                is_active=True,
            )
        else:
            # 样本集模式：使用 _resolve_sids
            resolved_sids = self._resolve_sids(
                query.sids, query.src_codes, query.symbols, query.asof
            )

        if not resolved_sids:
            raise ValueError("无法解析出有效的 SID")

        # 2. 解析日期参数（字符串 -> date 对象）
        start_date: date | None = None
        end_date: date | None = None
        asof_date: date | None = None

        if query.start:
            start_date = date.fromisoformat(query.start)
        if query.end:
            end_date = date.fromisoformat(query.end)
        if query.asof:
            asof_date = date.fromisoformat(query.asof)

        # 3. 确定资产类别
        asset_class: Literal["stock", "etf", "index"] | None = query.asset_class
        if not asset_class:
            asset_class = self._detect_asset_class_from_sids(resolved_sids)

        return _ResolvedQuery(
            sids=resolved_sids,
            start=start_date,
            end=end_date,
            asof=asof_date,
            asset_class=asset_class,
        )

    def _load_bars_core(self, resolved: _ResolvedQuery) -> pl.DataFrame:
        """
        加载核心行情数据（不含复权和增强）。

        Args:
            resolved: 解析后的查询参数。

        Returns:
            原始行情数据 DataFrame（不含复权和状态增强）。

        """
        # 确定数据集名称
        dataset = f"{resolved.asset_class}_daily"

        # 读取原始数据
        df = self._bars_store.read(
            dataset=dataset,
            sids=resolved.sids,
            start_date=resolved.start.isoformat() if resolved.start else None,
            end_date=resolved.end.isoformat() if resolved.end else None,
        )

        return df

    def _resolve_sids(
        self,
        sids: list[int] | None,
        src_codes: list[str] | None,
        symbols: list[str] | None,
        asof: str | None,
        source: str = "tushare",
    ) -> list[int]:
        """解析标识符为 SID 列表。"""
        resolved: set[int] = set()

        if sids:
            resolved.update(sids)

        if src_codes:
            mapping = self._security_store.resolve_sids_batch(src_codes, source, asof)
            resolved.update(mapping.values())

        if symbols:
            for symbol in symbols:
                sids_from_symbol = self._security_store.resolve_by_symbol(
                    symbol, source
                )
                resolved.update(sids_from_symbol)

        return sorted(resolved)

    def _detect_asset_class_from_sids(
        self, sids: list[int]
    ) -> Literal["stock", "etf", "index"]:
        """
        从 SID 列表检测资产类别。

        Args:
            sids: SID 列表。

        Returns:
            资产类别字符串（"stock", "etf", "index"）。

        Raises:
            ValueError: 如果检测到混合资产类别或无法识别。

        """
        stock_range = AssetSidRange.get_range("stock")
        etf_range = AssetSidRange.get_range("etf")
        index_range = AssetSidRange.get_range("index")

        # 检测每个资产类别
        has_stock = any(
            stock_range.min_sid <= sid <= stock_range.max_sid for sid in sids
        )
        has_etf = any(etf_range.min_sid <= sid <= etf_range.max_sid for sid in sids)
        has_index = any(
            index_range.min_sid <= sid <= index_range.max_sid for sid in sids
        )

        # 检测混合资产类别
        detected: list[Literal["stock", "etf", "index"]] = []
        if has_stock:
            detected.append("stock")
        if has_etf:
            detected.append("etf")
        if has_index:
            detected.append("index")

        if len(detected) > 1:
            display_names = {"stock": "stock", "etf": "ETF", "index": "index"}
            classes = [display_names[c] for c in detected]
            classes_str = ", ".join(classes)
            raise ValueError(
                "检测到混合资产类别查询。SID 包含 "
                + f"{classes_str}。请分别查询每个资产类别。"
            )

        if not detected:
            return "stock"  # 默认

        return detected[0]

    def _apply_adjustment(
        self,
        df: pl.DataFrame,
        adj: AdjType,
        resolved: _ResolvedQuery,
    ) -> pl.DataFrame:
        """
        应用价格调整（使用 _ResolvedQuery）。

        Args:
            df: K线数据 DataFrame。
            adj: 调整类型。
            resolved: 解析后的查询参数。

        Returns:
            调整后的 DataFrame。

        """
        # 读取调整因子
        adj_df = self._adj_factor_store.read(
            dataset="adj_factor",
            sids=resolved.sids,
            start_date=resolved.start.isoformat() if resolved.start else None,
            end_date=resolved.end.isoformat() if resolved.end else None,
        )

        if adj_df.is_empty():
            logger.warning(
                "No adjustment factor data available",
                event="bars_adj_not_available",
                adj_type=adj.value,
            )
            return df

        # 确保排序以正确处理 last() 聚合
        adj_df = adj_df.sort(["sid", "trade_date"])

        # PIT 安全：如果提供了 asof，可能需要过滤
        # - 有 knowledge_date：必须在 join 前过滤（PIT-safe）
        # - 无 knowledge_date：不在 join 前过滤（向后兼容，在 _apply_qfq_adj 中处理）
        join_adj_df = adj_df
        if resolved.asof is not None and "knowledge_date" in adj_df.columns:
            # 只保留在 asof 日期前已知的因子（这些因子才能出现在 join 结果中）
            join_adj_df = adj_df.filter(pl.col("knowledge_date") <= resolved.asof)

        # 关联调整因子（包含 knowledge_date）
        cols = ["sid", "trade_date", "adj_factor"]
        if "knowledge_date" in adj_df.columns:
            cols.append("knowledge_date")
        df = df.join(
            join_adj_df.select(cols),
            on=["sid", "trade_date"],
            how="left",
        )

        # 根据调整类型调用相应方法
        if adj == AdjType.QFQ:
            return apply_qfq_adj(df, adj_df, resolved.asof)
        else:  # HFQ
            return apply_hfq_adj(df, adj_df)

    def _enrich_with_status(
        self,
        df: pl.DataFrame,
        sids: list[int],
        start: date | str | None = None,
        end: date | str | None = None,
    ) -> pl.DataFrame:
        """
        使用股票状态信息增强行情数据（B.3）。

        与 stock_status 表关联添加：
        - is_suspended: 是否停牌
        - suspend_timing: 停牌时间段
        - is_st: 是否ST
        - st_type: ST类型
        - list_status: 上市状态

        Args:
            df: 行情数据 DataFrame。
            sids: 要获取状态的证券 ID 列表。
            start: 状态数据的起始日期（date 对象或字符串）。
            end: 状态数据的结束日期（date 对象或字符串）。

        Returns:
            添加了状态列的 DataFrame。

        """
        # 转换 date 对象为字符串（如果需要）
        start_str = start.isoformat() if isinstance(start, date) else start
        end_str = end.isoformat() if isinstance(end, date) else end

        # 读取状态数据
        status_df = self._stock_status_store.read(
            dataset="stock_status",
            sids=sids,
            start_date=start_str,
            end_date=end_str,
        )

        # 使用纯函数进行数据增强（新代码）
        return enrich_with_status(df, status_df, on=["sid", "trade_date"])
