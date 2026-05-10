"""Paper Trading Synchronizer 骨架 — 实盘时间同步器占位实现."""

from __future__ import annotations

from collections.abc import Iterator

from ditto_kernel.clock import Clock, RealtimeClock
from ditto_kernel.synchronizer import TimeSlice

__all__ = ["PaperSynchronizer"]


class PaperSynchronizer:
    """
    Paper Trading 时间同步器 — 实盘模式下的 Synchronizer 实现.

    骨架阶段：stream() 尚未实现，clock() 返回 RealtimeClock。
    满足 Synchronizer Protocol（结构化子类型）。
    """

    def stream(self) -> Iterator[TimeSlice]:
        """产生实时时间切片流（未实现）."""
        raise NotImplementedError("Paper Trading implementation pending")

    def clock(self) -> Clock:
        """返回实时时钟."""
        return RealtimeClock()
