"""Market subdomain — 时间语义、日历、粒度、宏观枚举、宏观数据接口。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

__all__ = [
    "CALENDAR_TO_TIMEZONE",
    "GRAIN_TO_TIME_KEYS",
    "CalendarId",
    "GrainId",
    "MacroCategory",
    "MacroDataProvider",
    "MacroFrequency",
    "TimeSpec",
]

type CalendarId = Literal["cn_stock"]
type GrainId = Literal["1d", "1m"]

GRAIN_TO_TIME_KEYS: dict[GrainId, tuple[str, ...]] = {
    "1d": ("trade_date",),
    "1m": ("trade_date", "bar_time"),
}

CALENDAR_TO_TIMEZONE: dict[CalendarId, str] = {
    "cn_stock": "Asia/Shanghai",
}


class MacroCategory(StrEnum):
    """宏观指标类别枚举。"""

    ECONOMIC = "economic"
    INTEREST_RATE = "interest_rate"
    EXCHANGE_RATE = "exchange_rate"
    MONEY_SUPPLY = "money_supply"
    PRICES = "prices"
    EMPLOYMENT = "employment"


class MacroFrequency(StrEnum):
    """宏观指标频率枚举。"""

    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass(frozen=True)
class TimeSpec:
    """时间语义规范。"""

    event_time_key: str
    availability_time_key: str | None = None

    @property
    def has_availability_time(self) -> bool:
        """是否指定可用时间键。"""
        return self.availability_time_key is not None


class MacroDataProvider(Protocol):
    """
    宏观指标数据提供者接口。

    零外部依赖签名 — 返回标准库类型。
    polars DataFrame 的组装由 data 层实现方负责。
    """

    def fetch_indicator(
        self, code: str, start: str, end: str
    ) -> list[dict[str, str | float]]:
        """获取指定宏观指标的时间序列。"""
        ...

    def list_indicators(self, category: str | None = None) -> list[dict[str, str]]:
        """列出可用的宏观指标。"""
        ...
