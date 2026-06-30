"""
PaperRuntimeKernel — Paper 交易运行时内核.

组合 RealtimeClock + SimpleEventBus，继承 _BaseRuntimeKernel 共享逻辑.
"""

from __future__ import annotations

from ditto_kernel.clock import RealtimeClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.runtime import BaseRuntimeKernel

__all__ = ["PaperRuntimeKernel"]


class PaperRuntimeKernel(BaseRuntimeKernel):
    """Paper 交易运行时内核 — RealtimeClock + SimpleEventBus."""

    _clock: RealtimeClock  # narrow: 构造器保证为 RealtimeClock

    def __init__(self) -> None:
        """
        初始化 Paper 交易运行时内核。

        使用 :class:`~ditto_kernel.clock.RealtimeClock` 和
        :class:`~ditto_kernel.events.SimpleEventBus` 构建 paper 交易运行时。

        """
        super().__init__(
            clock=RealtimeClock(),
            event_bus=SimpleEventBus(),
            mode="paper",
        )

    @property
    def clock(self) -> RealtimeClock:
        """实时时钟."""
        return self._clock
