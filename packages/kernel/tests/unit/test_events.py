"""ditto_kernel.events 单元测试."""

from datetime import datetime

import pytest
from ditto_kernel.events import DomainEvent, EventBus, EventName, SimpleEventBus


class TestDomainEvent:
    """DomainEvent 值对象测试."""

    def test_creation(self) -> None:
        """应正确创建事件."""
        event = DomainEvent(
            event_type="order_filled",
            timestamp=datetime(2024, 1, 15, 9, 30),
            payload={"order_id": "123", "fill_price": 10.5},
        )
        assert event.event_type == "order_filled"
        assert event.timestamp == datetime(2024, 1, 15, 9, 30)
        assert event.payload == {"order_id": "123", "fill_price": 10.5}

    def test_frozen(self) -> None:
        """DomainEvent 应为不可变."""
        event = DomainEvent(
            event_type="test",
            timestamp=datetime(2024, 1, 1),
            payload={},
        )
        with pytest.raises(AttributeError):
            event.event_type = "changed"  # type: ignore[misc]

    def test_default_payload(self) -> None:
        """payload 默认为空 dict."""
        event = DomainEvent(
            event_type="test",
            timestamp=datetime(2024, 1, 1),
        )
        assert event.payload == {}


class TestSimpleEventBus:
    """SimpleEventBus 测试."""

    def test_publish_calls_handlers(self) -> None:
        """发布事件应调用所有订阅的 handler."""
        bus = SimpleEventBus()
        received: list[DomainEvent] = []
        bus.subscribe("order_filled", received.append)
        event = DomainEvent(
            event_type="order_filled",
            timestamp=datetime(2024, 1, 15),
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0] is event

    def test_multiple_handlers(self) -> None:
        """同一事件的多个 handler 应按订阅顺序调用."""
        bus = SimpleEventBus()
        order: list[str] = []
        bus.subscribe("test", lambda e: order.append("first"))
        bus.subscribe("test", lambda e: order.append("second"))
        event = DomainEvent(event_type="test", timestamp=datetime(2024, 1, 1))
        bus.publish(event)
        assert order == ["first", "second"]

    def test_no_handler_no_error(self) -> None:
        """发布无 handler 的事件不应报错."""
        bus = SimpleEventBus()
        event = DomainEvent(event_type="unknown", timestamp=datetime(2024, 1, 1))
        bus.publish(event)  # 不应抛异常

    def test_handler_exception_propagates(self) -> None:
        """handler 异常应直接传播，不吞异常."""
        bus = SimpleEventBus()

        def bad_handler(event: DomainEvent) -> None:
            msg = "handler error"
            raise RuntimeError(msg)

        bus.subscribe("test", bad_handler)
        event = DomainEvent(event_type="test", timestamp=datetime(2024, 1, 1))
        with pytest.raises(RuntimeError, match="handler error"):
            bus.publish(event)

    def test_different_event_types(self) -> None:
        """不同事件类型的 handler 不应互相干扰."""
        bus = SimpleEventBus()
        received_a: list[DomainEvent] = []
        received_b: list[DomainEvent] = []
        bus.subscribe("type_a", received_a.append)
        bus.subscribe("type_b", received_b.append)

        event_a = DomainEvent(event_type="type_a", timestamp=datetime(2024, 1, 1))
        event_b = DomainEvent(event_type="type_b", timestamp=datetime(2024, 1, 1))

        bus.publish(event_a)
        bus.publish(event_b)

        assert len(received_a) == 1
        assert received_a[0].event_type == "type_a"
        assert len(received_b) == 1
        assert received_b[0].event_type == "type_b"


class TestEventBusProtocol:
    """EventBus Protocol 一致性测试."""

    def test_simple_event_bus_satisfies_protocol(self) -> None:
        """SimpleEventBus 应满足 EventBus Protocol."""
        bus: EventBus = SimpleEventBus()
        assert hasattr(bus, "publish")
        assert hasattr(bus, "subscribe")


class TestEventName:
    """EventName 事件名称常量 catalog 测试."""

    def test_all_known_event_names(self) -> None:
        """应包含所有已知事件名称常量."""
        expected = {
            "ORDER_SUBMITTED": "order_submitted",
            "ORDER_FILLED": "order_filled",
            "ORDER_CANCELED": "order_canceled",
            "RISK_GUARD_TRIGGERED": "risk_guard_triggered",
            "POSITION_CHANGED": "position_changed",
        }
        for attr, value in expected.items():
            assert getattr(EventName, attr) == value, f"EventName.{attr} 应为 {value!r}"

    def test_constants_are_strings(self) -> None:
        """所有常量应为 str 类型."""
        for attr in dir(EventName):
            if attr.isupper():
                assert isinstance(getattr(EventName, attr), str)
