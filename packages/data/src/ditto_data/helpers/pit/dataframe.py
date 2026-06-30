"""
PIT DataFrame 过滤模块.

提供 PIT 安全的 DataFrame 日期过滤逻辑。
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.helpers.pit.policy import (
    PIT_QUERY_OPERATOR,
    UnsafeResearchTimePolicy,
    is_trade_date_fallback_allowed,
)


def parse_asof_date(asof: date | str) -> date:
    """
    解析 asof 参数为 date 对象.

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
    unsafe_time_policy: UnsafeResearchTimePolicy | str | None = None,
) -> pl.DataFrame:
    """
    根据 PIT 日期过滤数据（优先使用 knowledge_date）.

    使用 PIT_QUERY_OPERATOR ("<=") 确保只使用 "已知" 的数据。

    Args:
        df: 输入 DataFrame。
        pit_dt: Point-in-Time 日期。
        date_column: 日期列名，默认 knowledge_date。
        unsafe_time_policy: 显式研究模式 unsafe 时间策略。

    Returns:
        过滤后的 DataFrame。

    """
    if date_column in df.columns:
        return df.filter(pl.col(date_column) <= pit_dt)

    if "trade_date" in df.columns:
        if not is_trade_date_fallback_allowed(unsafe_time_policy):
            msg = " ".join(
                (
                    f"PIT filter requires '{date_column}' column;",
                    "trade_date fallback is research-only.",
                    "Pass unsafe_time_policy=UnsafeResearchTimePolicy."
                    + "ALLOW_TRADE_DATE_FALLBACK to opt in.",
                )
            )
            raise ValueError(msg)
        logger.warning(
            f"Data missing {date_column}, using trade_date (not PIT-safe)",
            event="pit_missing_knowledge_date",
        )
        return df.filter(pl.col("trade_date") <= pit_dt)

    msg = " ".join(
        (
            f"PIT filter requires '{date_column}' column;",
            "no safe PIT date column is available.",
        )
    )
    raise ValueError(msg)


def get_pit_filter_expr(
    pit_dt: date,
    date_column: str = "knowledge_date",
) -> pl.Expr:
    """
    获取 PIT 过滤的 Polars 表达式.

    用于链式调用或复杂过滤场景。

    Args:
        pit_dt: Point-in-Time 日期。
        date_column: 日期列名，默认 knowledge_date。

    Returns:
        Polars 过滤表达式。

    Examples:
        >>> import polars as pl
        >>> from datetime import date
        >>> df.filter(get_pit_filter_expr(date(2024, 1, 15)))

    """
    return pl.col(date_column) <= pit_dt


__all__ = [
    "PIT_QUERY_OPERATOR",
    "filter_by_knowledge_date",
    "get_pit_filter_expr",
    "parse_asof_date",
]
