"""
Timezone utility functions for cross-market data handling.

Design reference: docs/plans/2026-02-27-global-asset-time-handling-design.md
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

import pytz

__all__ = [
    "MARKET_TIMEZONE_MAP",
    "convert_to_utc_midnight",
    "get_fred_query_date",
]

# 市场时区映射
MARKET_TIMEZONE_MAP: dict[str, str] = {
    "SSE": "Asia/Shanghai",  # 上交所
    "SZSE": "Asia/Shanghai",  # 深交所
    "NYSE": "America/New_York",  # 纽约证券交易所
    "NASDAQ": "America/New_York",  # 纳斯达克
    "CME": "America/Chicago",  # 芝加哥商品交易所
    "LME": "Europe/London",  # 伦敦金属交易所
    "FX": "America/New_York",  # 外汇（以 NY 收盘为界）
    "FRED": "America/New_York",  # FRED 数据
}


def convert_to_utc_midnight(
    trade_date: date,
    market: Literal["SSE", "SZSE", "NYSE", "NASDAQ", "CME", "LME", "FX", "FRED"],
) -> datetime:
    """
    将本地交易日期转换为 UTC 午夜时间戳.

    根据全球资产时间处理设计，采用 UTC 午夜（00:00:00）作为日线锚定时间。

    Args:
        trade_date: 本地交易日期
        market: 市场代码

    Returns:
        UTC 午夜时间戳（datetime with UTC timezone）

    """
    tz = pytz.timezone(MARKET_TIMEZONE_MAP[market])

    # 创建本地午夜时间，然后转换为 UTC
    local_midnight = tz.localize(
        datetime(trade_date.year, trade_date.month, trade_date.day, 0, 0, 0)
    )

    return local_midnight.astimezone(UTC)


def get_fred_query_date(beijing_trade_date: str) -> str:
    """
    将北京时间日期转换为 FRED 查询日期（美东时间）.

    摄取窗口通常在北京时间次日 05:00（美股收盘后），
    此时美东时间为前一日 16:00。

    Args:
        beijing_trade_date: 北京时间日期 (YYYY-MM-DD)

    Returns:
        美东时间日期 (YYYY-MM-DD)，通常为北京时间日期 - 1 天

    """
    beijing = pytz.timezone("Asia/Shanghai")
    dt = beijing.localize(datetime.strptime(beijing_trade_date, "%Y-%m-%d"))

    # 北京时间 00:00 = 美东时间前一日 11:00/12:00
    # 所以 FRED 查询日期 = 北京日期 - 1
    fred_date = dt - timedelta(days=1)
    return fred_date.strftime("%Y-%m-%d")
