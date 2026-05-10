"""
DomainEvent + EventBus Protocol + SimpleEventBus + EventName catalog.

满足 kernel Protocol/薄实现准入标准：
1. 预期跨层使用：core + data + port
2. 零业务逻辑：纯事件分发
3. 无外部依赖：仅标准库
4. SimpleEventBus 实现体 < 30 行
5. 无 I/O
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

__all__ = ["DomainEvent", "EventBus", "EventName", "SimpleEventBus"]

# Handler 类型：接收 DomainEvent 的回调
EventHandler = Callable[["DomainEvent"], None]


class EventName:
    """
    事件名称常量 — runtime spine 的事件名 catalog.

    所有领域事件的 event_type 值均在此定义，确保跨包引用的类型安全。
    消费者通过 ``from ditto_kernel.events import EventName`` 引用。
    """

    ORDER_SUBMITTED: str = "order_submitted"
    ORDER_FILLED: str = "order_filled"
    ORDER_CANCELED: str = "order_canceled"
    RISK_GUARD_TRIGGERED: str = "risk_guard_triggered"
    POSITION_CHANGED: str = "position_changed"
    ACCOUNT_UPDATED: str = "account_updated"
    STRATEGY_SIGNAL_GENERATED: str = "strategy_signal_generated"


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """
    领域事件.

    Attributes:
        event_type: 事件类型标识（如 EventName.ORDER_FILLED）
        timestamp: 事件发生时刻
        payload: 事件载荷（默认空字典）

    """

    event_type: str
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus(Protocol):
    """
    事件总线抽象.

    进程内同步分发，handler 按订阅顺序调用。
    """

    def publish(self, event: DomainEvent) -> None:
        """发布事件给所有订阅者."""
        ...

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅特定类型的事件."""
        ...


class SimpleEventBus:
    """
    简单事件总线 — 进程内同步分发.

    handler 按订阅顺序调用，handler 异常直接传播。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def publish(self, event: DomainEvent) -> None:
        """发布事件给所有订阅者."""
        for handler in self._handlers.get(event.event_type, []):
            handler(event)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅特定类型的事件."""
        self._handlers[event_type].append(handler)
