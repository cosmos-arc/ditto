"""
DomainEvent + EventBus Protocol + SimpleEventBus.

满足 kernel Protocol/薄实现准入标准：
1. 预期跨层使用：core + datahub + port
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

__all__ = ["DomainEvent", "EventBus", "SimpleEventBus"]

# Handler 类型：接收 DomainEvent 的回调
EventHandler = Callable[["DomainEvent"], None]


@dataclass(frozen=True)
class DomainEvent:
    """
    领域事件.

    Attributes:
        event_type: 事件类型标识（如 "order_filled", "risk_alert"）
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
