"""Paper Trading Synchronizer — 确定性时间切片同步器."""

from __future__ import annotations

from collections.abc import Iterator

from ditto_kernel.clock import Clock, RealtimeClock
from ditto_kernel.synchronizer import TimeSlice
from ditto_kernel.time_context import TimeContext

__all__ = ["PaperSynchronizer"]


class PaperSynchronizer:
    """
    Paper Trading 时间同步器 — 确定性时间切片版本.

    stream() 按 clock 当前时刻产生 TimeSlice，最小版本不模拟行情（bars 为空）。
    满足 Synchronizer Protocol（结构化子类型）。

    Args:
        clock: 时钟实例（默认 RealtimeClock，测试时传入 SimulatedClock）
        max_slices: 最大切片数（None = 无限流）

    """

    def __init__(
        self,
        clock: Clock | None = None,
        max_slices: int | None = None,
    ) -> None:
        self._clock = clock if clock is not None else RealtimeClock()
        self._max_slices = max_slices

    def stream(self) -> Iterator[TimeSlice]:
        """产生确定性时间切片流 — max_slices 有限时终止，None 时无限."""
        count = 0
        while self._max_slices is None or count < self._max_slices:
            now = self._clock.now()
            ctx = TimeContext(
                decision_time=now,
                knowledge_date=now.date(),
                trade_date=now.strftime("%Y-%m-%d"),
            )
            yield TimeSlice(time_context=ctx, bars={})
            count += 1

    def clock(self) -> Clock:
        """返回关联的时钟."""
        return self._clock
