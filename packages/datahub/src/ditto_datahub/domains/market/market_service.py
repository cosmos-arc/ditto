"""
MarketService - Market 域统一查询入口。

提供市场行情数据的统一查询接口，整合 Stock/ETF/Index 的 K线数据访问。
支持复权处理、状态关联等高级功能。

替换旧的 BarsAccessor 功能。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Literal

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.accessors.internal.adjustment import apply_hfq_adj, apply_qfq_adj
from ditto_datahub.accessors.internal.enrichment import enrich_with_status
from ditto_datahub.domains.market.etf.adj import EtfAdjFactorStore
from ditto_datahub.domains.market.etf.bars import EtfBarsStore
from ditto_datahub.domains.market.etf.nav import EtfNavStore
from ditto_datahub.domains.market.etf.status import EtfStatusStore
from ditto_datahub.domains.market.index.bars import IndexBarsStore
from ditto_datahub.domains.market.index.constituent import IndexConstituentStore
from ditto_datahub.domains.market.stock.adj import StockAdjFactorStore
from ditto_datahub.domains.market.stock.bars import StockBarsStore
from ditto_datahub.domains.market.stock.status import StockStatusStore
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.models import AssetSidRange


class AdjType(Enum):
    """复权类型."""

    NONE = "none"  # 不复权
    QFQ = "qfq"  # 前复权
    HFQ = "hfq"  # 后复权


@dataclass(frozen=True)
class MarketBarsQuery:
    """
    Market K线查询参数.

    Attributes:
        sids: SID 列表.
        start: 开始日期 (YYYY-MM-DD).
        end: 结束日期 (YYYY-MM-DD).
        adj: 复权类型（仅对 stock 数据有效，etf/index 数据不支持复权）.
        asof: 时间点查询日期 (PIT-safe).
        asset_class: 资产类别过滤.
        with_symbol: 是否在结果中添加 symbol 列.
        with_status: 是否添加股票状态信息（仅对股票数据有效）.
        raw: 是否跳过复权和状态增强.

    Note:
        - 复权功能 (adj) 仅支持股票数据，对 ETF 和 Index 数据无效
        - 状态增强 (with_status) 仅支持股票数据

    Examples:
        >>> query = MarketBarsQuery(sids=[1, 2, 3], start="2024-01-01")
        >>> service.get_bars(query)

    """

    sids: list[int]
    start: str | None = None
    end: str | None = None
    adj: AdjType = AdjType.NONE
    asof: str | None = None
    asset_class: Literal["stock", "etf", "index"] | None = None
    with_symbol: bool = False
    with_status: bool = False
    raw: bool = False


class MarketService:
    """
    Market 域统一查询服务.

    整合 Market 域所有 Store 的查询功能，提供统一的 K线查询接口。

    替代: BarsAccessor

    """

    def __init__(  # noqa: PLR0913
        self,
        stock_bars_store: StockBarsStore,
        stock_status_store: StockStatusStore,
        stock_adj_store: StockAdjFactorStore,
        etf_bars_store: EtfBarsStore,
        etf_status_store: EtfStatusStore,
        instrument_store: InstrumentStore,
        etf_nav_store: EtfNavStore | None = None,
        etf_adj_store: EtfAdjFactorStore | None = None,
        index_bars_store: IndexBarsStore | None = None,
        index_constituent_store: IndexConstituentStore | None = None,
    ) -> None:
        """
        初始化 MarketService.

        Args:
            stock_bars_store: 股票 K线存储.
            stock_status_store: 股票状态存储.
            stock_adj_store: 股票复权因子存储.
            etf_bars_store: ETF K线存储.
            etf_status_store: ETF 状态存储.
            instrument_store: 证券元数据存储.
            etf_nav_store: ETF 净值存储（可选）.
            etf_adj_store: ETF 复权因子存储（可选）.
            index_bars_store: 指数 K线存储（可选）.
            index_constituent_store: 指数成分股存储（可选）.

        """
        self._stock_bars_store = stock_bars_store
        self._stock_status_store = stock_status_store
        self._stock_adj_store = stock_adj_store
        self._etf_bars_store = etf_bars_store
        self._etf_status_store = etf_status_store
        self._instrument_store = instrument_store
        self._etf_nav_store = etf_nav_store
        self._etf_adj_store = etf_adj_store
        self._index_bars_store = index_bars_store
        self._index_constituent_store = index_constituent_store

    @traced("market.get_bars")
    def get_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """
        获取 K线数据.

        替代 BarsAccessor.get()

        Args:
            query: MarketBarsQuery 查询对象.

        Returns:
            K线数据 DataFrame.

        Raises:
            ValueError: 如果检测到混合资产类别查询.

        """
        logger.debug(
            "Fetching market bars data",
            event="market_bars_get_start",
            start=query.start,
            end=query.end,
            adj=query.adj.value,
            with_status=query.with_status,
        )

        # 1. 解析 SID 列表和资产类别
        sids, asset_class = self._resolve_sids_and_asset_class(query)

        # 空 SID 列表返回空 DataFrame
        if not sids:
            return pl.DataFrame()

        # 2. 解析日期参数（字符串 -> date 对象）
        start_date, end_date, asof_date = self._parse_dates(query)

        # 3. 加载核心数据
        df = self._load_bars_core(
            sids=sids,
            start=start_date,
            end=end_date,
            asset_class=asset_class,
        )

        if df.is_empty():
            return pl.DataFrame()

        # 4. 添加 symbol 列（如果需要）
        if query.with_symbol and not query.raw:
            df = self._instrument_store.enrich_with_symbol(df)

        # 5. 应用复权（如果需要且不是 raw 模式）
        if not query.raw and query.adj != AdjType.NONE and asset_class == "stock":
            df = self._apply_adjustment(
                df, query.adj, sids, start_date, end_date, asof_date
            )

        # 6. 添加状态列（如果需要且不是 raw 模式）
        if query.with_status and not query.raw and asset_class == "stock":
            df = self._enrich_with_status(df, sids, start_date, end_date)

        logger.debug(
            "Market bars data fetched",
            event="market_bars_get_complete",
            row_count=len(df),
            adj=query.adj.value,
        )

        # 记录指标
        M.data_records.add(
            len(df),
            {"dataset": "market_bars", "operation": "get", "adj": query.adj.value},
        )

        return df

    @traced("market.get_constituents")
    def get_constituents(
        self,
        index_sid: int,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数成分股（Point-in-Time）.

        Args:
            index_sid: 指数 SID.
            asof: 时点查询日期 (YYYY-MM-DD)，默认为当前日期.

        Returns:
            成分股 DataFrame，包含列: index_sid, stock_sid, effective_date, weight.

        Raises:
            NotImplementedError: 如果 IndexConstituentStore 未配置.

        Examples:
            >>> service.get_constituents(1, "2024-01-01")
            >>> service.get_constituents(1)  # 当前日期

        """
        if self._index_constituent_store is None:
            raise NotImplementedError(
                "IndexConstituentStore not configured. Please provide index_constituent_store when initializing MarketService.",  # noqa: E501
            )

        # 使用当前日期（如果未指定 asof）
        asof_date = asof or date.today().isoformat()

        logger.debug(
            "Fetching index constituents",
            event="market_constituents_get_start",
            index_sid=index_sid,
            asof=asof_date,
        )

        df = self._index_constituent_store.get(index_sid, asof_date)

        logger.debug(
            "Index constituents fetched",
            event="market_constituents_get_complete",
            index_sid=index_sid,
            asof=asof_date,
            row_count=len(df),
        )

        # 记录指标
        M.data_records.add(
            len(df),
            {"dataset": "market_constituents", "operation": "get"},
        )

        return df

    def _load_bars_core(
        self,
        sids: list[int],
        start: date | None,
        end: date | None,
        asset_class: Literal["stock", "etf", "index"],
    ) -> pl.DataFrame:
        """
        加载核心行情数据（不含复权和增强）.

        Args:
            sids: SID 列表.
            start: 开始日期.
            end: 结束日期.
            asset_class: 资产类别.

        Returns:
            原始行情数据 DataFrame.

        """
        start_str = start.isoformat() if start else None
        end_str = end.isoformat() if end else None

        if asset_class == "stock":
            return self._stock_bars_store.read(
                sids=sids,
                start_date=start_str,
                end_date=end_str,
            )
        elif asset_class == "etf":
            return self._etf_bars_store.read(
                sids=sids,
                start_date=start_str,
                end_date=end_str,
            )
        elif asset_class == "index":
            if self._index_bars_store is None:
                return pl.DataFrame()
            return self._index_bars_store.read(
                sids=sids,
                start_date=start_str,
                end_date=end_str,
            )
        else:
            return pl.DataFrame()

    def _detect_asset_class_from_sids(
        self, sids: list[int]
    ) -> Literal["stock", "etf", "index"]:
        """
        从 SID 列表检测资产类别.

        Args:
            sids: SID 列表.

        Returns:
            资产类别字符串（"stock", "etf", "index"）.

        Raises:
            ValueError: 如果检测到混合资产类别或无法识别.

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
                f"检测到混合资产类别查询。SID 包含 {classes_str}。请分别查询每个资产类别。",  # noqa: E501
            )

        if not detected:
            return "stock"  # 默认

        return detected[0]

    def _resolve_sids_and_asset_class(
        self, query: MarketBarsQuery
    ) -> tuple[list[int], Literal["stock", "etf", "index"]]:
        """
        解析 SID 列表和资产类别.

        Args:
            query: MarketBarsQuery 查询对象.

        Returns:
            (SID 列表, 资产类别).

        Raises:
            ValueError: 如果显式指定的 asset_class 与从 SID 检测出的不一致.

        """
        if not query.sids:
            # 空 SID 列表时，使用显式 asset_class（如果有），否则默认为 "stock"
            return [], query.asset_class or "stock"
        # 普通模式：使用指定的 SID
        sids = sorted(set(query.sids))
        asset_class = query.asset_class

        if asset_class:
            # 验证显式 asset_class 与从 SID 检测出的类别是否一致
            detected = self._detect_asset_class_from_sids(sids)
            if detected != asset_class:
                raise ValueError(
                    f"显式指定的资产类别 '{asset_class}' 与从 SID 检测出的类别 '{detected}' 不一致",  # noqa: E501
                )
        else:
            asset_class = self._detect_asset_class_from_sids(sids)

        return sids, asset_class

    def _parse_dates(
        self, query: MarketBarsQuery
    ) -> tuple[date | None, date | None, date | None]:
        """
        解析日期参数.

        Args:
            query: MarketBarsQuery 查询对象.

        Returns:
            (start_date, end_date, asof_date).

        """
        start_date: date | None = None
        if query.start:
            start_date = date.fromisoformat(query.start)

        end_date: date | None = None
        if query.end:
            end_date = date.fromisoformat(query.end)

        asof_date: date | None = None
        if query.asof:
            asof_date = date.fromisoformat(query.asof)

        return start_date, end_date, asof_date

    def _apply_adjustment(
        self,
        df: pl.DataFrame,
        adj: AdjType,
        sids: list[int],
        start: date | None,
        end: date | None,
        asof: date | None,
    ) -> pl.DataFrame:
        """
        应用价格调整.

        Args:
            df: K线数据 DataFrame.
            adj: 调整类型.
            sids: SID 列表.
            start: 开始日期.
            end: 结束日期.
            asof: Point-in-Time 查询日期.

        Returns:
            调整后的 DataFrame.

        """
        # 读取调整因子
        start_str = start.isoformat() if start else None
        end_str = end.isoformat() if end else None

        adj_df = self._stock_adj_store.read(
            sids=sids,
            start_date=start_str,
            end_date=end_str,
        )

        if adj_df.is_empty():
            # 对于 ETF 和 Index，没有复权因子是正常情况
            logger.info(
                "No adjustment factor data available (normal for ETF/Index)",
                event="market_bars_adj_not_available",
                adj_type=adj.value,
            )
            return df

        # 确保排序以正确处理 last() 聚合
        adj_df = adj_df.sort(["sid", "trade_date"])

        # PIT 安全：如果提供了 asof，可能需要过滤
        join_adj_df = adj_df
        if asof is not None and "knowledge_date" in adj_df.columns:
            # 只保留在 asof 日期前已知的因子
            join_adj_df = adj_df.filter(pl.col("knowledge_date") <= asof)

        # 关联调整因子
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
            return apply_qfq_adj(df, adj_df, asof)
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
        使用股票状态信息增强行情数据.

        添加：
        - is_suspended: 是否停牌
        - suspend_timing: 停牌时间段
        - is_st: 是否ST
        - st_type: ST类型
        - list_status: 上市状态

        Args:
            df: 行情数据 DataFrame.
            sids: 要获取状态的证券 ID 列表.
            start: 状态数据的起始日期（date 对象或字符串）.
            end: 状态数据的结束日期（date 对象或字符串）.

        Returns:
            添加了状态列的 DataFrame.

        """
        # 转换 date 对象为字符串（如果需要）
        start_str = start.isoformat() if isinstance(start, date) else start
        end_str = end.isoformat() if isinstance(end, date) else end

        # 读取状态数据
        status_df = self._stock_status_store.read(
            sids=sids,
            start_date=start_str,
            end_date=end_str,
        )

        # 使用纯函数进行数据增强
        return enrich_with_status(df, status_df, on=["sid", "trade_date"])
