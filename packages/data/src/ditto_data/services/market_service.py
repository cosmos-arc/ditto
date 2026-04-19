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
from typing import TYPE_CHECKING

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_data.helpers.adjustment import apply_hfq_adj, apply_qfq_adj
from ditto_data.models import InstrumentIdRange

if TYPE_CHECKING:
    from ditto_data.services.deps import MarketReaders
from ditto_data.storage.market.commodity.bars import CommodityBarsReader
from ditto_data.storage.market.etf.bars import EtfBarsReader
from ditto_data.storage.market.fx.bars import FxBarsReader
from ditto_data.storage.market.index.bars import IndexBarsReader
from ditto_data.storage.market.stock.bars import StockBarsReader

type _BarsReader = (
    StockBarsReader
    | EtfBarsReader
    | IndexBarsReader
    | FxBarsReader
    | CommodityBarsReader
)


class AdjType(Enum):
    """复权类型."""

    NONE = "none"  # 不复权
    QFQ = "qfq"  # 前复权
    HFQ = "hfq"  # 后复权

    @classmethod
    def from_string(cls, value: str) -> AdjType:
        """
        从字符串解析复权类型.

        Args:
            value: 字符串值 ("none", "qfq", "hfq")

        Returns:
            对应的 AdjType 枚举值，默认返回 NONE

        """
        return {"none": cls.NONE, "qfq": cls.QFQ, "hfq": cls.HFQ}.get(
            value.lower(), cls.NONE
        )


@dataclass(frozen=True)
class MarketBarsQuery:
    """
    Market K线查询参数.

    Attributes:
        instrument_ids: Instrument ID 列表（为 None 时配合 market_wide=True
            获取全市场数据）.
        start: 开始日期 (YYYY-MM-DD).
        end: 结束日期 (YYYY-MM-DD).
        adj: 复权类型（仅对 stock 数据有效，etf/index 数据不支持复权）.
        asof: 时间点查询日期 (PIT-safe).
        asset_class: 资产类别过滤.
        with_ticker: 是否在结果中添加 ticker 列.
        with_status: 是否添加股票状态信息（仅对股票数据有效）.
        raw: 是否跳过复权和状态增强.
        market_wide: 全市场查询模式。为 True 且 instrument_ids 为空时获取所有活跃证券.
        limit: 返回数量限制（在 DataFrame 层应用）.

    Note:
        - 复权功能 (adj) 仅支持股票数据，对 ETF 和 Index 数据无效
        - 状态增强 (with_status) 仅支持股票数据

    Examples:
        >>> query = MarketBarsQuery(instrument_ids=[1, 2, 3], start="2024-01-01")
        >>> service.get_bars(query)
        >>> query = MarketBarsQuery(market_wide=True, asset_class="stock")
        >>> service.get_bars(query)

    """

    instrument_ids: list[int] | None = None
    start: str | None = None
    end: str | None = None
    adj: AdjType = AdjType.NONE
    asof: str | None = None
    asset_class: str | None = None
    with_ticker: bool = False
    with_status: bool = False
    raw: bool = False
    market_wide: bool = False
    limit: int | None = None


@dataclass(frozen=True)
class MarketConstituentsQuery:
    """指数成分股查询参数."""

    index_instrument_id: int
    asof: str | None = None


type MarketQuery = MarketBarsQuery | MarketConstituentsQuery


class MarketService:
    """
    Market 域统一查询服务.

    整合 Market 域所有 Store 的查询功能，提供统一的 K线查询接口。

    替代: BarsAccessor

    """

    def __init__(
        self,
        read_ports: MarketReaders,
    ) -> None:
        """
        初始化 MarketService.

        Args:
            read_ports: Market 域读取依赖（包含所有 Reader）.

        """
        self._read_ports = read_ports

    @traced("market.find_bars")
    def find_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """K线查询入口."""
        return self._query_bars(query)

    @traced("market.list_bars")
    def list_bars(
        self,
        instrument_ids: list[int],
        start: str | None = None,
        end: str | None = None,
        adj: AdjType = AdjType.NONE,
        with_ticker: bool = False,
        with_status: bool = False,
        asset_class: str | None = None,
        limit: int | None = None,
    ) -> pl.DataFrame:
        """
        便利方法：批量查询K线数据.

        Args:
            instrument_ids: Instrument ID 列表.
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).
            adj: 复权类型（仅对 stock 数据有效）.
            with_ticker: 是否在结果中添加 ticker 列.
            with_status: 是否添加股票状态信息（仅对股票数据有效）.
            asset_class: 资产类别（显式指定可跳过自动检测）.
            limit: 返回数量限制（在 DataFrame 层应用）.

        Returns:
            K线数据 DataFrame.

        """
        query = MarketBarsQuery(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            adj=adj,
            with_ticker=with_ticker,
            with_status=with_status,
            asset_class=asset_class,
            limit=limit,
        )
        return self._query_bars(query)

    def _query_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """执行 K线查询."""
        logger.debug(
            "Fetching market bars data",
            event="market_bars_get_start",
            start=query.start,
            end=query.end,
            adj=query.adj.value,
            with_status=query.with_status,
        )

        # 1. 解析 Instrument ID 列表和资产类别
        instrument_ids, asset_class = self._resolve_instrument_ids_and_asset_class(
            query
        )

        # 空 Instrument ID 列表返回空 DataFrame（非 market_wide 模式）
        if not query.market_wide and not instrument_ids:
            return pl.DataFrame()

        # 2. 解析日期参数（字符串 -> date 对象）
        start_date, end_date, asof_date = self._parse_dates(query)

        # 3. 加载核心数据
        df = self._load_bars_core(
            instrument_ids=instrument_ids,
            start=start_date,
            end=end_date,
            asset_class=asset_class,
        )

        if df.is_empty():
            return pl.DataFrame()

        # 4. 添加 ticker 列（如果需要）
        if query.with_ticker and not query.raw:
            df = self._enrich_with_ticker(df)

        # 5. 应用复权（如果需要且不是 raw 模式）
        if not query.raw and query.adj != AdjType.NONE and asset_class == "stock":
            df = self._apply_adjustment(
                df, query.adj, instrument_ids, start_date, end_date, asof_date
            )

        # 6. 添加状态列（如果需要且不是 raw 模式）
        if query.with_status and not query.raw and asset_class == "stock":
            df = self._enrich_with_status(df, instrument_ids, start_date, end_date)

        logger.debug(
            "Market bars data fetched",
            event="market_bars_get_complete",
            row_count=len(df),
            adj=query.adj.value,
        )

        # 记录指标
        Metrics.data_records.add(
            len(df),
            {"dataset": "market_bars", "operation": "get", "adj": query.adj.value},
        )

        # P1-2: 在 DataFrame 层应用 limit
        if query.limit is not None:
            df = df.head(query.limit)

        return df

    @traced("market.get_constituents")
    def get_constituents(
        self,
        index_instrument_id: int,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """指数成分股查询入口."""
        return self._query_constituents(
            MarketConstituentsQuery(index_instrument_id=index_instrument_id, asof=asof)
        )

    def _query_constituents(self, query: MarketConstituentsQuery) -> pl.DataFrame:
        """执行指数成分股查询."""
        if self._read_ports.index_constituent is None:
            msg = (
                "IndexConstituentReader not configured. "
                "Please provide index_constituent when "
                "initializing MarketReaders."
            )
            raise NotImplementedError(msg)

        # 使用当前日期（如果未指定 asof）
        asof_date = query.asof or date.today().isoformat()

        logger.debug(
            "Fetching index constituents",
            event="market_constituents_get_start",
            index_instrument_id=query.index_instrument_id,
            asof=asof_date,
        )

        df = self._read_ports.index_constituent.get(
            query.index_instrument_id, asof_date
        )

        logger.debug(
            "Index constituents fetched",
            event="market_constituents_get_complete",
            index_instrument_id=query.index_instrument_id,
            asof=asof_date,
            row_count=len(df),
        )

        # 记录指标
        Metrics.data_records.add(
            len(df),
            {"dataset": "market_constituents", "operation": "get"},
        )

        return df

    def _load_bars_core(
        self,
        instrument_ids: list[int],
        start: date | None,
        end: date | None,
        asset_class: str,
    ) -> pl.DataFrame:
        """
        加载核心行情数据（不含复权和增强）.

        Args:
            instrument_ids: Instrument ID 列表.
            start: 开始日期.
            end: 结束日期.
            asset_class: 资产类别.

        Returns:
            原始行情数据 DataFrame.

        """
        start_str = start.isoformat() if start else None
        end_str = end.isoformat() if end else None

        reader = self._get_bars_reader(asset_class)
        if reader is None:
            return pl.DataFrame()

        return reader.read(
            instrument_ids=instrument_ids,
            start_date=start_str,
            end_date=end_str,
        )

    def _get_bars_reader(
        self,
        asset_class: str,
    ) -> _BarsReader | None:
        """
        获取指定资产类别的 K线读取器.

        Args:
            asset_class: 资产类别 ("stock", "etf", "index", "fx", "commodity").

        Returns:
            对应的 Reader 实例，如果未配置则返回 None.

        """
        # 必需依赖：stock 和 etf 始终可用
        if asset_class == "stock":
            return self._read_ports.stock_bars
        if asset_class == "etf":
            return self._read_ports.etf_bars

        # 可选依赖：index / fx / commodity 可能未配置
        optional_readers = {
            "index": self._read_ports.index_bars,
            "fx": self._read_ports.fx_bars,
            "commodity": self._read_ports.commodity_bars,
        }
        return optional_readers.get(asset_class)

    def _resolve_instrument_ids_and_asset_class(
        self, query: MarketBarsQuery
    ) -> tuple[list[int], str]:
        """
        解析 Instrument ID 列表和资产类别.

        Args:
            query: MarketBarsQuery 查询对象.

        Returns:
            (Instrument ID 列表, 资产类别).

        Raises:
            ValueError: 如果显式指定的 asset_class 与从 Instrument ID 检测出的不一致.

        """
        if query.market_wide:
            # 全市场模式：获取所有活跃 Instrument ID
            asset_class = query.asset_class
            instrument_ids = sorted(
                self._read_ports.instrument.list_instrument_ids(asset_class=asset_class)
            )
            if not asset_class:
                asset_class = (
                    InstrumentIdRange.detect_asset_class(instrument_ids)
                    if instrument_ids
                    else "stock"
                )
            return instrument_ids, asset_class
        elif not query.instrument_ids:
            # 空 Instrument ID 列表时，使用显式 asset_class（如果有）
            # 否则默认为 "stock"
            return [], query.asset_class or "stock"

        # 普通模式：使用指定的 Instrument ID
        instrument_ids = sorted(set(query.instrument_ids))
        asset_class = query.asset_class

        if asset_class:
            # 验证显式 asset_class 与从 Instrument ID 检测出的类别是否一致
            detected = InstrumentIdRange.detect_asset_class(instrument_ids)
            if detected != asset_class:
                msg = (
                    f"显式指定的资产类别 '{asset_class}' 与从 Instrument ID "
                    f"检测出的类别 '{detected}' 不一致"
                )
                raise ValueError(msg)
        else:
            asset_class = InstrumentIdRange.detect_asset_class(instrument_ids)

        return instrument_ids, asset_class

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
        instrument_ids: list[int],
        start: date | None,
        end: date | None,
        asof: date | None,
    ) -> pl.DataFrame:
        """
        应用价格调整.

        Args:
            df: K线数据 DataFrame.
            adj: 调整类型.
            instrument_ids: Instrument ID 列表.
            start: 开始日期.
            end: 结束日期.
            asof: Point-in-Time 查询日期.

        Returns:
            调整后的 DataFrame.

        """
        # 读取调整因子
        start_str = start.isoformat() if start else None
        end_str = end.isoformat() if end else None

        adj_df = self._read_ports.stock_adj.read(
            instrument_ids=instrument_ids,
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
        adj_df = adj_df.sort(["instrument_id", "trade_date"])

        # PIT 安全：如果提供了 asof，可能需要过滤
        join_adj_df = adj_df
        if asof is not None and "knowledge_date" in adj_df.columns:
            # 只保留在 asof 日期前已知的因子
            join_adj_df = adj_df.filter(pl.col("knowledge_date") <= asof)

        # 关联调整因子
        cols = ["instrument_id", "trade_date", "adj_factor"]
        if "knowledge_date" in adj_df.columns:
            cols.append("knowledge_date")
        df = df.join(
            join_adj_df.select(cols),
            on=["instrument_id", "trade_date"],
            how="left",
        )

        # 根据调整类型调用相应方法
        if adj == AdjType.QFQ:
            return apply_qfq_adj(df, adj_df, asof)
        else:  # HFQ
            return apply_hfq_adj(df, adj_df)

    def _apply_etf_adjustment(
        self,
        df: pl.DataFrame,
        adj: AdjType,
        start: str,
        end: str,
    ) -> pl.DataFrame:
        """
        应用 ETF 价格调整.

        与 _apply_adjustment() 类似，但使用 etf_adj 依赖读取复权因子。
        当 adj_df 为空时，优雅回退返回原始数据。

        Args:
            df: ETF K线数据 DataFrame.
            adj: 调整类型.
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            调整后的 DataFrame（无复权因子时返回原始数据）.

        """
        etf_adj = self._read_ports.etf_adj
        if etf_adj is None:
            logger.warning(
                "etf_adj port not configured, returning raw data",
                event="market_etf_bars_adj_not_available",
                adj_type=adj.value,
            )
            return df

        adj_df = etf_adj.read(start_date=start, end_date=end)

        if adj_df.is_empty():
            logger.warning(
                "No ETF adjustment factor data available, returning raw data",
                event="market_etf_bars_adj_not_available",
                adj_type=adj.value,
            )
            return df

        # 确保排序以正确处理 last() 聚合
        adj_df = adj_df.sort(["instrument_id", "trade_date"])

        # 关联调整因子
        cols = ["instrument_id", "trade_date", "adj_factor"]
        if "knowledge_date" in adj_df.columns:
            cols.append("knowledge_date")
        df = df.join(
            adj_df.select(cols),
            on=["instrument_id", "trade_date"],
            how="left",
        )

        # 根据调整类型调用相应方法
        if adj == AdjType.QFQ:
            return apply_qfq_adj(df, adj_df)
        else:  # HFQ
            return apply_hfq_adj(df, adj_df)

    def _enrich_with_status(
        self,
        df: pl.DataFrame,
        instrument_ids: list[int],
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
            instrument_ids: 要获取状态的证券 ID 列表.
            start: 状态数据的起始日期（date 对象或字符串）.
            end: 状态数据的结束日期（date 对象或字符串）.

        Returns:
            添加了状态列的 DataFrame.

        """
        # 转换 date 对象为字符串（如果需要）
        start_str = start.isoformat() if isinstance(start, date) else start
        end_str = end.isoformat() if isinstance(end, date) else end

        # 读取状态数据
        status_df = self._read_ports.stock_status.read(
            instrument_ids=instrument_ids,
            start_date=start_str,
            end_date=end_str,
        )

        # 内联数据增强：join 状态数据
        return df.join(status_df, on=["instrument_id", "trade_date"], how="left")

    def _enrich_with_ticker(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        使用 ticker 信息增强 DataFrame.

        Args:
            df: 包含 instrument_id 列的 DataFrame.

        Returns:
            添加了 ticker 列的 DataFrame.

        """
        id_col = "instrument_id"
        if id_col not in df.columns or df.is_empty():
            return df

        instrument_ids = df[id_col].unique().to_list()
        ticker_map = self._read_ports.instrument.get_instrument_id_ticker_map(
            instrument_ids
        )

        # 空 ticker_map 时的防护：直接添加全 null 的 ticker 列
        if not ticker_map:
            return df.with_columns(pl.lit(None, dtype=pl.String).alias("ticker"))

        ticker_df = pl.DataFrame(
            {
                id_col: list(ticker_map.keys()),
                "ticker": list(ticker_map.values()),
            },
            schema_overrides={id_col: pl.Int64, "ticker": pl.String},
        )

        # 内联数据增强：join ticker 数据
        return df.join(ticker_df, on=id_col, how="left")

    @traced("market.get_stock_bars")
    def get_stock_bars(self, start: str, end: str) -> pl.DataFrame:
        """
        查询全市场股票日K线（不复权）.

        提供公开的行情查询接口，供 RuntimeDerivedInputProvider 等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部证券的原始行情。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            原始行情 DataFrame，包含 instrument_id、trade_date、open、high、
            low、close、pre_close、volume、amount 等列。

        """
        logger.debug(
            "Fetching stock daily bars",
            event="market_stock_bars_get_start",
            start=start,
            end=end,
        )

        df = self._read_ports.stock_bars.read(start_date=start, end_date=end)

        logger.debug(
            "Stock daily bars fetched",
            event="market_stock_bars_get_complete",
            row_count=len(df),
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "stock_daily", "operation": "get"},
        )

        return df

    @traced("market.get_etf_bars")
    def get_etf_bars(self, start: str, end: str, adj: str = "none") -> pl.DataFrame:
        """
        查询全市场 ETF 日K线，可选复权.

        提供公开的行情查询接口，供 ETF 因子评估等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部 ETF 的行情数据。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).
            adj: 复权类型 ("none", "qfq", "hfq")，默认不复权。

        Returns:
            行情 DataFrame，包含 instrument_id、trade_date、open、high、
            low、close、volume、amount 等列。如果请求复权但无复权因子
            数据，则返回未复权的原始数据。

        """
        logger.debug(
            "Fetching ETF daily bars",
            event="market_etf_bars_get_start",
            start=start,
            end=end,
            adj=adj,
        )

        df = self._read_ports.etf_bars.read(start_date=start, end_date=end)

        # 应用复权（如果需要且 etf_adj 依赖可用）
        adj_type = AdjType.from_string(adj)
        if adj_type != AdjType.NONE and self._read_ports.etf_adj is not None:
            df = self._apply_etf_adjustment(df, adj_type, start, end)

        logger.debug(
            "ETF daily bars fetched",
            event="market_etf_bars_get_complete",
            row_count=len(df),
            adj=adj,
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "etf_daily", "operation": "get", "adj": adj},
        )

        return df

    @traced("market.get_adj_factors")
    def get_adj_factors(self, start: str, end: str) -> pl.DataFrame:
        """
        查询股票复权因子.

        提供公开的 adj_factor 查询接口，
        供 RuntimeDerivedInputProvider 等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部证券的复权因子。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            复权因子 DataFrame，包含 instrument_id、trade_date、adj_factor 等列。

        """
        logger.debug(
            "Fetching adjustment factors",
            event="market_adj_factors_get_start",
            start=start,
            end=end,
        )

        df = self._read_ports.stock_adj.read(start_date=start, end_date=end)

        logger.debug(
            "Adjustment factors fetched",
            event="market_adj_factors_get_complete",
            row_count=len(df),
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "adj_factor", "operation": "get"},
        )

        return df

    @traced("market.get_stock_status")
    def get_stock_status(self, start: str, end: str) -> pl.DataFrame:
        """
        查询股票状态.

        提供公开的 stock_status 查询接口，
        供 RuntimeDerivedInputProvider 等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部证券的状态数据。

        状态包含：is_suspended、suspend_timing、is_st、st_type、list_status。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            股票状态 DataFrame，包含 instrument_id、trade_date、is_suspended 等列。

        """
        logger.debug(
            "Fetching stock status",
            event="market_stock_status_get_start",
            start=start,
            end=end,
        )

        df = self._read_ports.stock_status.read(start_date=start, end_date=end)

        logger.debug(
            "Stock status fetched",
            event="market_stock_status_get_complete",
            row_count=len(df),
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "stock_status", "operation": "get"},
        )

        return df
