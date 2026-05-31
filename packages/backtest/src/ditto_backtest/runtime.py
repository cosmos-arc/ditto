"""
BacktestRuntimeKernel — 回测运行时内核.

组合 SimulatedClock + SimpleEventBus，实现 TradingRuntimeKernel Protocol.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.runtime import (
    RuntimeLifecycle,
    RuntimeSnapshot,
    validate_transition,
)

__all__ = ["BacktestRuntimeKernel"]


class BacktestRuntimeKernel:
    """回测运行时内核 — SimulatedClock + SimpleEventBus."""

    def __init__(self, start_date: str) -> None:
        self._clock = self._build_clock(start_date)
        self._event_bus = SimpleEventBus()
        self._lifecycle = RuntimeLifecycle.PRE_INITIALIZED
        self._started_at: datetime | None = None

    @property
    def clock(self) -> SimulatedClock:
        """回测模拟时钟."""
        return self._clock

    @property
    def event_bus(self) -> SimpleEventBus:
        """事件总线."""
        return self._event_bus

    @property
    def lifecycle(self) -> RuntimeLifecycle:
        """当前生命周期状态."""
        return self._lifecycle

    @property
    def state(self) -> RuntimeSnapshot:
        """不可变状态快照."""
        return RuntimeSnapshot(
            state=self._lifecycle,
            mode="backtest",
            started_at=self._started_at,
        )

    def transition_to(self, target: RuntimeLifecycle) -> None:
        """转换到目标生命周期状态."""
        validate_transition(self._lifecycle, target)
        if target == RuntimeLifecycle.RUNNING and self._started_at is None:
            self._started_at = datetime.now(UTC)
        self._lifecycle = target

    @staticmethod
    def _build_clock(start_date: str) -> SimulatedClock:
        d = date.fromisoformat(start_date)
        return SimulatedClock(initial=datetime(d.year, d.month, d.day, tzinfo=UTC))
