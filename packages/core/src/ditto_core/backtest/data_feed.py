"""
DataFeed — 市场数据切片协议 + 数据容器.

MarketSnapshot 从 execution/reality/market.py 导入.
Slice 是某日所有标的的聚合视图, 由 DataFeed 提供.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_kernel.identity import InstrumentId

from ditto_core.execution.reality.market import MarketSnapshot

__all__ = ["DataFeed", "MarketSnapshot", "Slice"]


# ---------------------------------------------------------------------------
# Slice
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Slice:
    """
    某日所有标的的聚合视图.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        step_time: 回测步骤时间
        bars: instrument_id → MarketSnapshot
        benchmark_close: 基准收盘价 (None = 无基准)

    """

    trade_date: str
    step_time: datetime
    bars: dict[InstrumentId, MarketSnapshot]
    benchmark_close: float | None = None


# ---------------------------------------------------------------------------
# DataFeed Protocol
# ---------------------------------------------------------------------------


class DataFeed(Protocol):
    """市场数据源协议 — 提供交易日历和逐日切片。"""

    def trading_days(self) -> list[str]:
        """返回回测区间内的交易日列表 (YYYY-MM-DD)。"""
        ...

    def get_slice(self, date: str) -> Slice:
        """获取指定日期的市场数据切片。"""
        ...
