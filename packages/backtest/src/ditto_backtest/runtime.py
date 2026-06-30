"""
BacktestRuntimeKernel — 回测运行时内核.

组合 SimulatedClock + SimpleEventBus，继承 _BaseRuntimeKernel 共享逻辑.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.runtime import BaseRuntimeKernel

__all__ = ["BacktestRuntimeKernel"]


class BacktestRuntimeKernel(BaseRuntimeKernel):
    """回测运行时内核 — SimulatedClock + SimpleEventBus."""

    _clock: SimulatedClock  # narrow: 构造器保证为 SimulatedClock

    def __init__(self, start_date: str) -> None:
        """
        初始化回测运行时内核。

        Args:
            start_date: 回测起始日期（ISO 8601 格式，如 ``"2024-01-01"``），
                用于构建 :class:`~ditto_kernel.clock.SimulatedClock` 初始时刻。

        """
        super().__init__(
            clock=self._build_clock(start_date),
            event_bus=SimpleEventBus(),
            mode="backtest",
        )

    @property
    def clock(self) -> SimulatedClock:
        """回测模拟时钟."""
        return self._clock

    @staticmethod
    def _build_clock(start_date: str) -> SimulatedClock:
        d = date.fromisoformat(start_date)
        return SimulatedClock(initial=datetime(d.year, d.month, d.day, tzinfo=UTC))
