"""OrderEventJournal Protocol + InMemoryOrderEventJournal。"""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol, runtime_checkable

from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId

__all__ = ["InMemoryOrderEventJournal", "OrderEventJournal"]


@runtime_checkable
class OrderEventJournal(Protocol):
    """订单事件日志 — 追踪订单生命周期事件。"""

    def append(self, event: OrderEvent) -> None:
        """追加事件。"""
        ...

    def events_for(self, client_id: ClientOrderId) -> tuple[OrderEvent, ...]:
        """获取指定订单的全部事件。"""
        ...

    def all_events(self) -> tuple[OrderEvent, ...]:
        """获取全部事件。"""
        ...


class InMemoryOrderEventJournal:
    """内存实现 — 用于回测和测试。"""

    def __init__(self) -> None:
        self._events: dict[str, list[OrderEvent]] = defaultdict(list)

    def append(self, event: OrderEvent) -> None:
        """追加事件。"""
        self._events[event.client_id.value].append(event)

    def events_for(self, client_id: ClientOrderId) -> tuple[OrderEvent, ...]:
        """获取指定订单的全部事件。"""
        return tuple(self._events.get(client_id.value, ()))

    def all_events(self) -> tuple[OrderEvent, ...]:
        """获取全部事件。"""
        all_events: list[OrderEvent] = []
        for events in self._events.values():
            all_events.extend(events)
        return tuple(all_events)
