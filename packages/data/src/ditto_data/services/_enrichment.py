"""
数据增强辅助函数 — 从 MarketService 提取的状态/Ticker 增强逻辑.

提供 enrich_with_status 和 enrich_with_ticker 模块级函数，
供 MarketService._enrich_with_status / _enrich_with_ticker 委托调用。
"""

from __future__ import annotations

from datetime import date

import polars as pl

from ditto_data.services.deps import MarketReaders


def enrich_with_status(
    df: pl.DataFrame,
    instrument_ids: list[int],
    readers: MarketReaders,
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
        readers: Market 域读取依赖.
        start: 状态数据的起始日期（date 对象或字符串）.
        end: 状态数据的结束日期（date 对象或字符串）.

    Returns:
        添加了状态列的 DataFrame.

    """
    # 转换 date 对象为字符串（如果需要）
    start_str = start.isoformat() if isinstance(start, date) else start
    end_str = end.isoformat() if isinstance(end, date) else end

    # 读取状态数据
    status_df = readers.stock_status.read(
        instrument_ids=instrument_ids,
        start_date=start_str,
        end_date=end_str,
    )

    # 内联数据增强：join 状态数据
    return df.join(status_df, on=["instrument_id", "trade_date"], how="left")


def enrich_with_ticker(
    df: pl.DataFrame,
    readers: MarketReaders,
) -> pl.DataFrame:
    """
    使用 ticker 信息增强 DataFrame.

    Args:
        df: 包含 instrument_id 列的 DataFrame.
        readers: Market 域读取依赖.

    Returns:
        添加了 ticker 列的 DataFrame.

    """
    id_col = "instrument_id"
    if id_col not in df.columns or df.is_empty():
        return df

    instrument_ids = df[id_col].unique().to_list()
    ticker_map = readers.instrument.get_instrument_id_ticker_map(instrument_ids)

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
