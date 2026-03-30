"""
Clock Protocol + 薄实现.

满足 kernel Protocol/薄实现准入标准：
1. 预期跨层使用: core + datahub + port
2. 零业务逻辑: 纯时间抽象
3. 无外部依赖: 仅 datetime 标准库
4. 实现体 < 30 行
5. 无 I/O
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

__all__ = ["Clock", "RealtimeClock", "SimulatedClock"]


class Clock(Protocol):
    """
    统一时间抽象.

    回测和实盘通过不同的 Clock 实现共享同一代码路径。
    """

    def now(self) -> datetime:
        """当前时刻."""
        ...

    def today(self) -> date:
        """当前日期."""
        ...

    def advance_to(self, target: datetime) -> None:
        """推进到目标时刻."""
        ...


class SimulatedClock:
    """回测时钟 -- 可推进的模拟时间."""

    def __init__(self, initial: datetime) -> None:
        self._current = initial

    def now(self) -> datetime:
        """当前时刻."""
        return self._current

    def today(self) -> date:
        """当前日期."""
        return self._current.date()

    def advance_to(self, target: datetime) -> None:
        """推进到目标时刻."""
        if target < self._current:
            msg = f"模拟时钟不能回退: {self._current} -> {target}"
            raise ValueError(msg)
        self._current = target


class RealtimeClock:
    """实时时钟 -- 读取系统时间."""

    def now(self) -> datetime:
        """当前时刻."""
        return datetime.now()

    def today(self) -> date:
        """当前日期."""
        return date.today()

    def advance_to(self, target: datetime) -> None:
        """实时时钟不支持 advance_to."""
        msg = "实时时钟不支持 advance_to"
        raise RuntimeError(msg)
