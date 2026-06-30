"""ditto_backtest.runtime 单元测试."""

import pytest
from ditto_backtest.runtime import BacktestRuntimeKernel
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.runtime import RuntimeLifecycle, RuntimeSnapshot, TradingRuntimeKernel


class TestBacktestRuntimeKernelProtocol:
    """BacktestRuntimeKernel 应满足 TradingRuntimeKernel Protocol."""

    def test_satisfies_protocol(self) -> None:
        """isinstance 检查应通过."""
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")
        assert isinstance(kernel, TradingRuntimeKernel)

    def test_initial_lifecycle(self) -> None:
        """初始状态应为 PRE_INITIALIZED."""
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")
        assert kernel.lifecycle == RuntimeLifecycle.PRE_INITIALIZED

    def test_clock_returns_simulated(self) -> None:
        """clock 应返回 SimulatedClock."""
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")
        assert isinstance(kernel.clock, SimulatedClock)

    def test_event_bus_returns_simple(self) -> None:
        """event_bus 应返回 SimpleEventBus."""
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")
        assert isinstance(kernel.event_bus, SimpleEventBus)

    def test_state_returns_snapshot(self) -> None:
        """state 应返回 RuntimeSnapshot."""
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")
        snap = kernel.state
        assert isinstance(snap, RuntimeSnapshot)
        assert snap.state == RuntimeLifecycle.PRE_INITIALIZED
        assert snap.mode == "backtest"


class TestBacktestRuntimeKernelTransitions:
    """BacktestRuntimeKernel 状态转换测试."""

    def test_full_lifecycle(self) -> None:
        """完整生命周期."""
        # PRE_INITIALIZED → READY → STARTING → RUNNING → STOPPING → STOPPED
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")

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
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")
        with pytest.raises(RuntimeError, match="非法状态转换"):
            kernel.transition_to(RuntimeLifecycle.RUNNING)

    def test_state_tracks_mode(self) -> None:
        """state.mode 应始终为 backtest."""
        kernel = BacktestRuntimeKernel(start_date="2024-01-01")
        assert kernel.state.mode == "backtest"
        kernel.transition_to(RuntimeLifecycle.READY)
        assert kernel.state.mode == "backtest"
