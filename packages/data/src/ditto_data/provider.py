"""
DataProvider Protocol + 查询契约.

Kernel 零外部依赖约束禁止 import polars，因此 Protocol 定义位于 ditto_data。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import polars as pl

__all__ = ["BarQuery", "DataProvider", "InstrumentQuery"]


@dataclass(frozen=True)
class BarQuery:
    """
    行情查询契约.

    Attributes:
        instruments: 标的代码列表（如 "000001.SZ"）
        start: 开始日期（ISO 格式 "YYYY-MM-DD"）
        end: 结束日期（ISO 格式 "YYYY-MM-DD"）
        frequency: 频率（"daily" / "weekly" / "monthly"），由实现侧验证
        adj: 复权类型（"none" / "hfq" / "qfq"），由实现侧验证

    """

    instruments: tuple[str, ...]
    start: str
    end: str
    frequency: str = "daily"
    adj: str = "none"

    def __init__(
        self,
        *,
        instruments: list[str] | tuple[str, ...],
        start: str,
        end: str,
        frequency: str = "daily",
        adj: str = "none",
    ) -> None:
        object.__setattr__(self, "instruments", tuple(instruments))
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "frequency", frequency)
        object.__setattr__(self, "adj", adj)


@dataclass(frozen=True)
class InstrumentQuery:
    """
    标的查询契约.

    所有字段均可 None，表示"不筛选"。

    Attributes:
        asset_class: 资产类型（"stock" / "etf" / ...）
        exchange: 交易所（"XSHE" / "XSHG" / "XBSE"）
        universe: 成分股宇宙（"hs300" / "zz500" / ...）

    """

    asset_class: str | None = None
    exchange: str | None = None
    universe: str | None = None


class DataProvider(Protocol):
    """统一数据访问抽象."""

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        """获取行情数据."""
        ...

    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        """获取标的列表."""
        ...

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        """获取交易日历."""
        ...

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
    ) -> pl.DataFrame:
        """获取因子数据."""
        ...
