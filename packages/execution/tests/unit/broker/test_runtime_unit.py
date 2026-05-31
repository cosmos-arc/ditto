"""ditto_execution.broker.runtime 单元测试."""

from datetime import UTC, datetime

import pytest
from ditto_execution.broker.runtime import PaperRuntimeKernel
from ditto_kernel.clock import RealtimeClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.runtime import RuntimeLifecycle, RuntimeSnapshot, TradingRuntimeKernel


class TestPaperRuntimeKernelProtocol:
    """PaperRuntimeKernel 应满足 TradingRuntimeKernel Protocol."""

    def test_satisfies_protocol(self) -> None:
        """isinstance 检查应通过."""
        kernel = PaperRuntimeKernel()
        assert isinstance(kernel, TradingRuntimeKernel)

    def test_initial_lifecycle(self) -> None:
        """初始状态应为 PRE_INITIALIZED."""
        kernel = PaperRuntimeKernel()
        assert kernel.lifecycle == RuntimeLifecycle.PRE_INITIALIZED

    def test_clock_returns_realtime(self) -> None:
        """clock 应返回 RealtimeClock."""
        kernel = PaperRuntimeKernel()
        assert isinstance(kernel.clock, RealtimeClock)

    def test_event_bus_returns_simple(self) -> None:
        """event_bus 应返回 SimpleEventBus."""
        kernel = PaperRuntimeKernel()
        assert isinstance(kernel.event_bus, SimpleEventBus)

    def test_event_bus_publish_subscribe(self) -> None:
        """event_bus 发布/订阅应正常工作."""
        kernel = PaperRuntimeKernel()
        bus = kernel.event_bus
        received: list[object] = []
        bus.subscribe("test", received.append)
        from ditto_kernel.events import DomainEvent

        event = DomainEvent(
            event_type="test",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        )
        bus.publish(event)
        assert len(received) == 1

    def test_state_returns_snapshot(self) -> None:
        """state 应返回 RuntimeSnapshot."""
        kernel = PaperRuntimeKernel()
        snap = kernel.state
        assert isinstance(snap, RuntimeSnapshot)
        assert snap.state == RuntimeLifecycle.PRE_INITIALIZED
        assert snap.mode == "paper"


class TestPaperRuntimeKernelTransitions:
    """PaperRuntimeKernel 状态转换测试."""

    def test_full_lifecycle(self) -> None:
        """完整生命周期."""
        # PRE_INITIALIZED → READY → STARTING → RUNNING → STOPPING → STOPPED
        kernel = PaperRuntimeKernel()

        kernel.transition_to(RuntimeLifecycle.READY)
        assert kernel.lifecycle == RuntimeLifecycle.READY

        kernel.transition_to(RuntimeLifecycle.STARTING)
        assert kernel.lifecycle == RuntimeLifecycle.STARTING

        kernel.transition_to(RuntimeLifecycle.RUNNING)
        assert kernel.lifecycle == RuntimeLifecycle.RUNNING
        assert kernel.state.started_at is not None

        kernel.transition_to(RuntimeLifecycle.STOPPING)
        assert kernel.lifecycle == RuntimeLifecycle.STOPPING

        kernel.transition_to(RuntimeLifecycle.STOPPED)
        assert kernel.lifecycle == RuntimeLifecycle.STOPPED

    def test_invalid_transition_raises(self) -> None:
        """非法转换应抛 RuntimeError."""
        kernel = PaperRuntimeKernel()
        with pytest.raises(RuntimeError, match="非法状态转换"):
            kernel.transition_to(RuntimeLifecycle.RUNNING)

    def test_state_tracks_mode(self) -> None:
        """state.mode 应始终为 paper."""
        kernel = PaperRuntimeKernel()
        assert kernel.state.mode == "paper"
        kernel.transition_to(RuntimeLifecycle.READY)
        assert kernel.state.mode == "paper"
