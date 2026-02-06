"""
PIT (Point-in-Time) 查询纯函数模块。

提供 PIT 安全的日期过滤逻辑。
"""

from datetime import date

import polars as pl
from ditto_foundation import logger


def parse_asof_date(asof: date | str) -> date:
    """
    解析 asof 参数为 date 对象。

    Args:
        asof: date 对象或 ISO 格式字符串。

    Returns:
        解析后的 date 对象。

    """
    if isinstance(asof, str):
        return date.fromisoformat(asof)
    return asof


def filter_by_knowledge_date(
    df: pl.DataFrame,
    pit_dt: date,
    date_column: str = "knowledge_date",
) -> pl.DataFrame:
    """
    根据 PIT 日期过滤数据（优先使用 knowledge_date）。

    Args:
        df: 输入 DataFrame。
        pit_dt: Point-in-Time 日期。
        date_column: 日期列名，默认 knowledge_date。

    Returns:
        过滤后的 DataFrame。

    """
    if date_column in df.columns:
        return df.filter(pl.col(date_column) <= pit_dt)

    # Fallback to trade_date (会记录警告)
    if "trade_date" in df.columns:
        logger.warning(
            f"Data missing {date_column}, using trade_date (not PIT-safe)",
            event="pit_missing_knowledge_date",
        )
        return df.filter(pl.col("trade_date") <= pit_dt)

    return df
