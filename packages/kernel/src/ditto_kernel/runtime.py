"""
RuntimeLifecycle FSM + RuntimeSnapshot + TradingRuntimeKernel Protocol.

满足 kernel Protocol/薄实现准入标准：
1. 预期跨层使用：backtest + execution（Phase 0）
2. 零业务逻辑：纯状态机定义
3. 无外部依赖：仅标准库
4. 无 I/O

参考：NautilusTrader ComponentState FSM
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus

__all__ = ["RuntimeLifecycle", "RuntimeSnapshot", "TradingRuntimeKernel"]


class RuntimeLifecycle(StrEnum):
    """运行时生命周期 FSM — 8 稳态 + 7 过渡态."""

    PRE_INITIALIZED = "pre_initialized"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    RESUMING = "resuming"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RESETTING = "resetting"
    DISPOSING = "disposing"
    DISPOSED = "disposed"
    DEGRADING = "degrading"
    DEGRADED = "degraded"
    FAULTING = "faulting"
    FAULTED = "faulted"


@dataclass(frozen=True, kw_only=True)
class RuntimeSnapshot:
    """不可变运行时状态快照."""

    state: RuntimeLifecycle
    mode: str  # "backtest" | "paper" | "live"
    started_at: datetime | None = None
    error: str | None = None


_TRANSITIONS: dict[RuntimeLifecycle, frozenset[RuntimeLifecycle]] = {
    RuntimeLifecycle.PRE_INITIALIZED: frozenset({RuntimeLifecycle.READY}),
    RuntimeLifecycle.READY: frozenset({RuntimeLifecycle.STARTING}),
    RuntimeLifecycle.STARTING: frozenset(
        {
            RuntimeLifecycle.RUNNING,
            RuntimeLifecycle.FAULTED,
        }
    ),
    RuntimeLifecycle.RUNNING: frozenset(
        {
            RuntimeLifecycle.PAUSED,
            RuntimeLifecycle.STOPPING,
            RuntimeLifecycle.DEGRADING,
            RuntimeLifecycle.FAULTING,
        }
    ),
    RuntimeLifecycle.PAUSED: frozenset(
        {
            RuntimeLifecycle.RESUMING,
            RuntimeLifecycle.STOPPING,
            RuntimeLifecycle.FAULTING,
        }
    ),
    RuntimeLifecycle.RESUMING: frozenset(
        {
            RuntimeLifecycle.RUNNING,
            RuntimeLifecycle.FAULTED,
        }
    ),
    RuntimeLifecycle.STOPPING: frozenset(
        {
            RuntimeLifecycle.STOPPED,
            RuntimeLifecycle.FAULTED,
        }
    ),
    RuntimeLifecycle.STOPPED: frozenset(
        {
            RuntimeLifecycle.RESETTING,
            RuntimeLifecycle.DISPOSING,
        }
    ),
    RuntimeLifecycle.RESETTING: frozenset(
        {
            RuntimeLifecycle.READY,
            RuntimeLifecycle.FAULTED,
        }
    ),
    RuntimeLifecycle.DEGRADING: frozenset(
        {
            RuntimeLifecycle.DEGRADED,
            RuntimeLifecycle.FAULTED,
        }
    ),
    RuntimeLifecycle.DEGRADED: frozenset(
        {
            RuntimeLifecycle.RESUMING,
            RuntimeLifecycle.STOPPING,
            RuntimeLifecycle.FAULTING,
        }
    ),
    RuntimeLifecycle.FAULTING: frozenset({RuntimeLifecycle.FAULTED}),
    RuntimeLifecycle.DISPOSING: frozenset({RuntimeLifecycle.DISPOSED}),
    RuntimeLifecycle.FAULTED: frozenset(),
    RuntimeLifecycle.DISPOSED: frozenset(),
}


def validate_transition(current: RuntimeLifecycle, target: RuntimeLifecycle) -> None:
    """验证状态转换合法性，非法抛 RuntimeError."""
    allowed = _TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        msg = f"非法状态转换: {current.value} → {target.value}"
        raise RuntimeError(msg)


@runtime_checkable
class TradingRuntimeKernel(Protocol):
    """交易运行时内核 — Clock + EventBus + Lifecycle + State."""

    @property
    def clock(self) -> Clock:
        """统一时间抽象."""
        ...

    @property
    def event_bus(self) -> EventBus:
        """事件总线."""
        ...

    @property
    def lifecycle(self) -> RuntimeLifecycle:
        """当前生命周期状态."""
        ...

    @property
    def state(self) -> RuntimeSnapshot:
        """不可变状态快照."""
        ...

    def transition_to(self, target: RuntimeLifecycle) -> None:
        """转换到目标生命周期状态."""
        ...
