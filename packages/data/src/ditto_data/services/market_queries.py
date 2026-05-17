"""
Market 查询类型定义与查询执行函数.

从 MarketService 提取的查询参数 dataclass 和查询执行函数。
AdjType 定义在 market_types.py 以避免 market_queries ↔ market_adjustment 循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl
from ditto_platform.foundation import Metrics, logger

from ditto_data.models import InstrumentIdRange
from ditto_data.services._enrichment import enrich_with_status, enrich_with_ticker
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_adjustment import apply_adjustment
from ditto_data.services.market_types import AdjType
from ditto_data.storage.market.commodity.bars import CommodityBarsReader
from ditto_data.storage.market.etf.bars import EtfBarsReader
from ditto_data.storage.market.fx.bars import FxBarsReader
from ditto_data.storage.market.index.bars import IndexBarsReader
from ditto_data.storage.market.stock.bars import StockBarsReader

__all__ = [
    "AdjType",
    "BarsReader",
    "MarketBarsQuery",
    "MarketConstituentsQuery",
    "MarketQuery",
    "get_bars_reader",
    "load_bars_core",
    "parse_dates",
    "query_bars",
    "query_constituents",
    "resolve_ids_and_class",
]


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

type BarsReader = (
    StockBarsReader
    | EtfBarsReader
    | IndexBarsReader
    | FxBarsReader
    | CommodityBarsReader
)


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def parse_dates(
    query: MarketBarsQuery,
) -> tuple[date | None, date | None, date | None]:
    """解析日期参数（字符串 -> date 对象）."""
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


# ---------------------------------------------------------------------------
# Reader 路由与数据加载
# ---------------------------------------------------------------------------


def get_bars_reader(
    asset_class: str,
    read_ports: MarketReaders,
) -> BarsReader | None:
    """获取指定资产类别的 K线读取器."""
    if asset_class == "stock":
        return read_ports.stock_bars
    if asset_class == "etf":
        return read_ports.etf_bars

    optional_readers = {
        "index": read_ports.index_bars,
        "fx": read_ports.fx_bars,
        "commodity": read_ports.commodity_bars,
    }
    return optional_readers.get(asset_class)


def resolve_ids_and_class(
    query: MarketBarsQuery,
    read_ports: MarketReaders,
) -> tuple[list[int], str]:
    """解析 Instrument ID 列表和资产类别."""
    if query.market_wide:
        asset_class = query.asset_class
        instrument_ids = sorted(
            read_ports.instrument.list_instrument_ids(asset_class=asset_class)
        )
        if not asset_class:
            asset_class = (
                InstrumentIdRange.detect_asset_class(instrument_ids)
                if instrument_ids
                else "stock"
            )
        return instrument_ids, asset_class
    elif not query.instrument_ids:
        return [], query.asset_class or "stock"

    instrument_ids = sorted(set(query.instrument_ids))
    asset_class = query.asset_class

    if asset_class:
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


def load_bars_core(
    instrument_ids: list[int],
    start: date | None,
    end: date | None,
    asset_class: str,
    read_ports: MarketReaders,
) -> pl.DataFrame:
    """加载核心行情数据（不含复权和增强）."""
    start_str = start.isoformat() if start else None
    end_str = end.isoformat() if end else None

    reader = get_bars_reader(asset_class, read_ports)
    if reader is None:
        return pl.DataFrame()

    return reader.read(
        instrument_ids=instrument_ids,
        start_date=start_str,
        end_date=end_str,
    )


# ---------------------------------------------------------------------------
# 核心查询编排
# ---------------------------------------------------------------------------


def query_bars(query: MarketBarsQuery, read_ports: MarketReaders) -> pl.DataFrame:
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
    instrument_ids, asset_class = resolve_ids_and_class(query, read_ports)

    # 空 Instrument ID 列表返回空 DataFrame（非 market_wide 模式）
    if not query.market_wide and not instrument_ids:
        return pl.DataFrame()

    # 2. 解析日期参数（字符串 -> date 对象）
    start_date, end_date, asof_date = parse_dates(query)

    # 3. 加载核心数据
    df = load_bars_core(
        instrument_ids=instrument_ids,
        start=start_date,
        end=end_date,
        asset_class=asset_class,
        read_ports=read_ports,
    )

    if df.is_empty():
        return pl.DataFrame()

    # 4. 添加 ticker 列（如果需要）
    if query.with_ticker and not query.raw:
        df = enrich_with_ticker(df, read_ports)

    # 5. 应用复权（如果需要且不是 raw 模式）
    if not query.raw and query.adj != AdjType.NONE and asset_class == "stock":
        df = apply_adjustment(
            df,
            query.adj,
            instrument_ids,
            start_date,
            end_date,
            asof_date,
            read_ports,
        )

    # 6. 添加状态列（如果需要且不是 raw 模式）
    if query.with_status and not query.raw and asset_class == "stock":
        df = enrich_with_status(df, instrument_ids, read_ports, start_date, end_date)

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

    if query.limit is not None:
        df = df.head(query.limit)

    return df


def query_constituents(
    query: MarketConstituentsQuery, read_ports: MarketReaders
) -> pl.DataFrame:
    """执行指数成分股查询."""
    if read_ports.index_constituent is None:
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

    df = read_ports.index_constituent.get(query.index_instrument_id, asof_date)

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
