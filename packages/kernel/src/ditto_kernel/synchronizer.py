"""时间同步器 — 回测/实盘切换的核心 seam."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from ditto_kernel.clock import Clock
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_context import TimeContext
from ditto_kernel.trading import MarketSnapshot

__all__ = ["Synchronizer", "TimeSlice"]


@dataclass(frozen=True)
class TimeSlice:
    """
    单步时间切片 — Synchronizer 每次产出的最小数据单元.

    包含该时刻的所有可用市场数据。
    不包含账户/策略/订单状态（这些由 step chain 内部管理）。

    Attributes:
        time_context: 时间上下文（PIT 语义）
        bars: instrument_id → MarketSnapshot
        benchmark_close: 与 bars 同一 PIT 边界下的可选基准收盘价
        source_snapshot_ids: 与 bars 同一 PIT 边界下的上游数据快照 ID

    """

    time_context: TimeContext
    bars: dict[InstrumentId, MarketSnapshot]
    benchmark_close: float | None = None
    source_snapshot_ids: dict[InstrumentId, str] = field(default_factory=dict)


class Synchronizer(Protocol):
    """
    时间同步器 — 回测/实盘切换的唯一 seam.

    封装「何时推进时间」+「该时刻有什么数据」为一元化抽象。
    主循环永远不知道自己的模式。

    对标 LEAN ISynchronizer.StreamData() → IEnumerable<TimeSlice>.
    """

    def stream(self) -> Iterator[TimeSlice]:
        """产生时间切片流 — 回测时有限，实盘时无限."""
        ...

    def clock(self) -> Clock:
        """返回与此同步器关联的时钟."""
        ...
