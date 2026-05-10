"""
Market 复权调整函数 — 从 MarketService 提取的独立调整逻辑.

提供 apply_adjustment 和 apply_etf_adjustment 模块级函数，
供 MarketService 委托调用。
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.helpers.adjustment import apply_hfq_adj, apply_qfq_adj
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_types import AdjType


def apply_adjustment(
    df: pl.DataFrame,
    adj: AdjType,
    instrument_ids: list[int],
    start: date | None,
    end: date | None,
    asof: date | None,
    readers: MarketReaders,
) -> pl.DataFrame:
    """
    应用股票价格调整.

    Args:
        df: K线数据 DataFrame.
        adj: 调整类型.
        instrument_ids: Instrument ID 列表.
        start: 开始日期.
        end: 结束日期.
        asof: Point-in-Time 查询日期.
        readers: Market 域读取依赖.

    Returns:
        调整后的 DataFrame.

    """
    # 读取调整因子
    start_str = start.isoformat() if start else None
    end_str = end.isoformat() if end else None

    adj_df = readers.stock_adj.read(
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


def apply_etf_adjustment(
    df: pl.DataFrame,
    adj: AdjType,
    start: str,
    end: str,
    readers: MarketReaders,
) -> pl.DataFrame:
    """
    应用 ETF 价格调整.

    与 apply_adjustment() 类似，但使用 etf_adj 依赖读取复权因子。
    当 adj_df 为空时，优雅回退返回原始数据。

    Args:
        df: ETF K线数据 DataFrame.
        adj: 调整类型.
        start: 开始日期 (YYYY-MM-DD).
        end: 结束日期 (YYYY-MM-DD).
        readers: Market 域读取依赖.

    Returns:
        调整后的 DataFrame（无复权因子时返回原始数据）.

    """
    etf_adj = readers.etf_adj
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
