"""BacktestService 集成测试 — 验证 SimulatedClock/EventBus 注入路径."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import DomainEvent, SimpleEventBus

# ---------------------------------------------------------------------------
# TestClockCreation
# ---------------------------------------------------------------------------


class TestClockCreation:
    """验证 SimulatedClock 正确创建并设置初始时间。"""

    def test_clock_initial_matches_start_date(self) -> None:
        """SimulatedClock 的初始时间应等于 config.start_date 的 UTC 午夜。"""
        start = date(2024, 1, 2)
        expected_initial = datetime(start.year, start.month, start.day, tzinfo=UTC)
        clock = SimulatedClock(initial=expected_initial)
        assert clock.now() == expected_initial

    def test_clock_today_returns_correct_date(self) -> None:
        """SimulatedClock.today() 应返回初始日期。"""
        start = date(2024, 1, 2)
        clock = SimulatedClock(
            initial=datetime(start.year, start.month, start.day, tzinfo=UTC)
        )
        assert clock.today() == start

    def test_clock_advance_to(self) -> None:
        """SimulatedClock.advance_to 应正确推进时间。"""
        start = datetime(2024, 1, 2, tzinfo=UTC)
        clock = SimulatedClock(initial=start)
        target = datetime(2024, 1, 3, tzinfo=UTC)
        clock.advance_to(target)
        assert clock.now() == target

    def test_clock_cannot_go_backward(self) -> None:
        """SimulatedClock 不允许时间回退。"""
        start = datetime(2024, 1, 3, tzinfo=UTC)
        clock = SimulatedClock(initial=start)
        with pytest.raises(ValueError, match="回退"):
            clock.advance_to(datetime(2024, 1, 2, tzinfo=UTC))

    def test_clock_advance_to_same_time_allowed(self) -> None:
        """SimulatedClock.advance_to 到相同时间应不报错。"""
        start = datetime(2024, 1, 2, tzinfo=UTC)
        clock = SimulatedClock(initial=start)
        clock.advance_to(start)  # 相同时间，不回退
        assert clock.now() == start


# ---------------------------------------------------------------------------
# TestEventBusCreation
# ---------------------------------------------------------------------------


class TestEventBusCreation:
    """验证 SimpleEventBus 正确创建和事件分发。"""

    def test_event_bus_created(self) -> None:
        """SimpleEventBus 应成功创建。"""
        event_bus = SimpleEventBus()
        assert event_bus is not None

    def test_event_bus_subscribe_and_publish(self) -> None:
        """SimpleEventBus 应支持订阅和发布。"""
        event_bus = SimpleEventBus()
        received: list[DomainEvent] = []

        def handler(event: DomainEvent) -> None:
            received.append(event)

        event_bus.subscribe("test_event", handler)
        event = DomainEvent(
            event_type="test_event",
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            payload={"key": "value"},
        )
        event_bus.publish(event)
        assert len(received) == 1
        assert received[0].event_type == "test_event"

    def test_event_bus_multiple_subscribers(self) -> None:
        """SimpleEventBus 应支持同一事件的多个订阅者。"""
        event_bus = SimpleEventBus()
        received_a: list[DomainEvent] = []
        received_b: list[DomainEvent] = []

        event_bus.subscribe("order_filled", received_a.append)
        event_bus.subscribe("order_filled", received_b.append)

        event = DomainEvent(
            event_type="order_filled",
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
        event_bus.publish(event)
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_event_bus_no_subscriber_no_error(self) -> None:
        """SimpleEventBus 发布无人订阅的事件时不报错。"""
        event_bus = SimpleEventBus()
        event = DomainEvent(
            event_type="unknown_event",
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
        event_bus.publish(event)  # 应不抛出异常


# ---------------------------------------------------------------------------
# TestEngineOptionsAssembly
# ---------------------------------------------------------------------------


class TestEngineOptionsAssembly:
    """验证 EngineOptions 正确组装 Clock 和 EventBus。"""

    def test_engine_options_accepts_event_bus(self) -> None:
        """EngineOptions 应接受 EventBus 参数。"""
        from ditto_backtest.engine import EngineOptions

        event_bus = SimpleEventBus()

        options = EngineOptions(
            event_bus=event_bus,
        )
        assert options.event_bus is event_bus

    def test_engine_options_defaults(self) -> None:
        """EngineOptions 默认值全部为 None。"""
        from ditto_backtest.engine import EngineOptions

        options = EngineOptions()
        assert options.event_bus is None
        assert options.fee_model is None

    def test_engine_options_frozen(self) -> None:
        """EngineOptions 是 frozen dataclass，创建后不可变。"""
        from dataclasses import FrozenInstanceError

        from ditto_backtest.engine import EngineOptions

        options = EngineOptions()
        with pytest.raises(FrozenInstanceError):
            options.event_bus = SimpleEventBus()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestClockEventBusIntegration
# ---------------------------------------------------------------------------


class TestClockEventBusIntegration:
    """验证 Clock + EventBus 在回测场景中的联合行为。"""

    def test_clock_ticks_drive_event_timestamps(self) -> None:
        """事件时间戳应与 Clock 推进保持一致。"""
        clock = SimulatedClock(initial=datetime(2024, 1, 2, tzinfo=UTC))
        event_bus = SimpleEventBus()
        timestamps: list[datetime] = []

        def capture_timestamp(event: DomainEvent) -> None:
            timestamps.append(event.timestamp)

        event_bus.subscribe("bar", capture_timestamp)

        # Day 1
        clock.advance_to(datetime(2024, 1, 3, tzinfo=UTC))
        event_bus.publish(
            DomainEvent(
                event_type="bar",
                timestamp=clock.now(),
            )
        )

        # Day 2
        clock.advance_to(datetime(2024, 1, 4, tzinfo=UTC))
        event_bus.publish(
            DomainEvent(
                event_type="bar",
                timestamp=clock.now(),
            )
        )

        assert len(timestamps) == 2
        assert timestamps[0] == datetime(2024, 1, 3, tzinfo=UTC)
        assert timestamps[1] == datetime(2024, 1, 4, tzinfo=UTC)
        # 事件严格按时间递增
        assert timestamps[0] < timestamps[1]
