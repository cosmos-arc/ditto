"""
DataProvider Protocol + 查询契约.

满足 kernel Protocol/薄实现准入标准：
1. 预期跨层使用：core + datahub + port
2. 零业务逻辑：纯接口定义 + 查询值对象
3. 无外部依赖：仅标准库
4. Protocol 无实现体（查询对象为 frozen dataclass）
5. 无 I/O
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

__all__ = ["AnyFrame", "BarQuery", "DataProvider", "InstrumentQuery"]

# Protocol 层不引入 polars 依赖，实际实现用 pl.DataFrame
AnyFrame = Any


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
    """
    统一数据访问抽象.

    所有平面通过此 Protocol 获取数据，不直接依赖存储实现。
    返回类型为 AnyFrame（Any），实现侧和消费者侧用 pl.DataFrame。
    """

    def get_bars(self, query: BarQuery) -> AnyFrame:
        """获取行情数据."""
        ...

    def get_instruments(self, query: InstrumentQuery) -> AnyFrame:
        """获取标的列表."""
        ...

    def get_schedule(self, start: str, end: str) -> AnyFrame:
        """获取交易日历."""
        ...

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
    ) -> AnyFrame:
        """获取因子数据."""
        ...
