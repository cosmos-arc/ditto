"""ditto_kernel.runtime 单元测试."""

from datetime import UTC, datetime

import pytest
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.runtime import (
    _TRANSITIONS,
    RuntimeLifecycle,
    RuntimeSnapshot,
    TradingRuntimeKernel,
    validate_transition,
)


class TestRuntimeLifecycle:
    """RuntimeLifecycle 枚举测试."""

    def test_stable_states(self) -> None:
        """应包含 8 个稳态."""
        stable = {
            RuntimeLifecycle.PRE_INITIALIZED,
            RuntimeLifecycle.READY,
            RuntimeLifecycle.RUNNING,
            RuntimeLifecycle.PAUSED,
            RuntimeLifecycle.STOPPED,
            RuntimeLifecycle.DEGRADED,
            RuntimeLifecycle.FAULTED,
            RuntimeLifecycle.DISPOSED,
        }
        assert len(stable) == 8

    def test_transition_states(self) -> None:
        """应包含 7 个过渡态."""
        transition = {
            RuntimeLifecycle.STARTING,
            RuntimeLifecycle.RESUMING,
            RuntimeLifecycle.STOPPING,
            RuntimeLifecycle.RESETTING,
            RuntimeLifecycle.DISPOSING,
            RuntimeLifecycle.DEGRADING,
            RuntimeLifecycle.FAULTING,
        }
        assert len(transition) == 7

    def test_total_count(self) -> None:
        """总共 15 个状态."""
        assert len(RuntimeLifecycle) == 15

    def test_is_str_enum(self) -> None:
        """应为 StrEnum，值是小写蛇形命名."""
        assert RuntimeLifecycle.RUNNING == "running"
        assert RuntimeLifecycle.PRE_INITIALIZED == "pre_initialized"
        assert RuntimeLifecycle.STOPPING == "stopping"

    def test_str_enum_compatibility(self) -> None:
        """StrEnum 成员应可直接用于字符串比较."""
        state = RuntimeLifecycle.RUNNING
        assert isinstance(state, str)
        assert state == "running"


class TestRuntimeSnapshot:
    """RuntimeSnapshot 值对象测试."""

    def test_creation(self) -> None:
        """应正确创建快照."""
        now = datetime(2024, 6, 15, tzinfo=UTC)
        snap = RuntimeSnapshot(
            state=RuntimeLifecycle.RUNNING,
            mode="backtest",
            started_at=now,
            error=None,
        )
        assert snap.state == RuntimeLifecycle.RUNNING
        assert snap.mode == "backtest"
        assert snap.started_at == now
        assert snap.error is None

    def test_frozen(self) -> None:
        """应为不可变."""
        snap = RuntimeSnapshot(
            state=RuntimeLifecycle.READY,
            mode="paper",
        )
        with pytest.raises(AttributeError):
            snap.state = RuntimeLifecycle.RUNNING  # type: ignore[misc]

    def test_defaults(self) -> None:
        """started_at 和 error 默认为 None."""
        snap = RuntimeSnapshot(
            state=RuntimeLifecycle.PRE_INITIALIZED,
            mode="backtest",
        )
        assert snap.started_at is None
        assert snap.error is None

    def test_with_error(self) -> None:
        """应能记录错误信息."""
        snap = RuntimeSnapshot(
            state=RuntimeLifecycle.FAULTED,
            mode="live",
            error="数据源断开",
        )
        assert snap.error == "数据源断开"


class TestTransitions:
    """转换表 + validate_transition 测试."""

    def test_valid_pre_initialized_to_ready(self) -> None:
        """PRE_INITIALIZED → READY 应合法."""
        validate_transition(RuntimeLifecycle.PRE_INITIALIZED, RuntimeLifecycle.READY)

    def test_valid_ready_to_starting(self) -> None:
        """READY → STARTING 应合法."""
        validate_transition(RuntimeLifecycle.READY, RuntimeLifecycle.STARTING)

    def test_valid_starting_to_running(self) -> None:
        """STARTING → RUNNING 应合法."""
        validate_transition(RuntimeLifecycle.STARTING, RuntimeLifecycle.RUNNING)

    def test_valid_starting_to_faulted(self) -> None:
        """STARTING → FAULTED 应合法."""
        validate_transition(RuntimeLifecycle.STARTING, RuntimeLifecycle.FAULTED)

    def test_valid_running_to_paused(self) -> None:
        """RUNNING → PAUSED 应合法."""
        validate_transition(RuntimeLifecycle.RUNNING, RuntimeLifecycle.PAUSED)

    def test_valid_running_to_stopping(self) -> None:
        """RUNNING → STOPPING 应合法."""
        validate_transition(RuntimeLifecycle.RUNNING, RuntimeLifecycle.STOPPING)

    def test_valid_running_to_degrading(self) -> None:
        """RUNNING → DEGRADING 应合法."""
        validate_transition(RuntimeLifecycle.RUNNING, RuntimeLifecycle.DEGRADING)

    def test_valid_running_to_faulting(self) -> None:
        """RUNNING → FAULTING 应合法."""
        validate_transition(RuntimeLifecycle.RUNNING, RuntimeLifecycle.FAULTING)

    def test_valid_stopped_to_resetting(self) -> None:
        """STOPPED → RESETTING 应合法."""
        validate_transition(RuntimeLifecycle.STOPPED, RuntimeLifecycle.RESETTING)

    def test_valid_stopped_to_disposing(self) -> None:
        """STOPPED → DISPOSING 应合法."""
        validate_transition(RuntimeLifecycle.STOPPED, RuntimeLifecycle.DISPOSING)

    def test_valid_disposing_to_disposed(self) -> None:
        """DISPOSING → DISPOSED 应合法."""
        validate_transition(RuntimeLifecycle.DISPOSING, RuntimeLifecycle.DISPOSED)

    def test_invalid_transition_raises(self) -> None:
        """非法转换应抛 RuntimeError."""
        with pytest.raises(RuntimeError, match="非法状态转换"):
            validate_transition(RuntimeLifecycle.RUNNING, RuntimeLifecycle.READY)

    def test_faulted_is_terminal(self) -> None:
        """FAULTED 不允许任何转换."""
        assert len(_TRANSITIONS.get(RuntimeLifecycle.FAULTED, frozenset())) == 0

    def test_disposed_is_terminal(self) -> None:
        """DISPOSED 不允许任何转换."""
        assert len(_TRANSITIONS.get(RuntimeLifecycle.DISPOSED, frozenset())) == 0

    def test_self_transition_invalid(self) -> None:
        """自身到自身的转换应非法（除 FAULTED/DISPOSED 外无自转）."""
        for state in RuntimeLifecycle:
            if state not in (RuntimeLifecycle.FAULTED, RuntimeLifecycle.DISPOSED):
                assert state not in _TRANSITIONS.get(state, frozenset()), (
                    f"{state.name} 不应允许自转"
                )


class TestTradingRuntimeKernelProtocol:
    """TradingRuntimeKernel Protocol conformance 测试."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Protocol 应支持 isinstance 检查."""

        class FakeKernel:
            def __init__(self) -> None:
                self._clock = SimulatedClock(datetime(2024, 1, 1, tzinfo=UTC))
                self._bus = SimpleEventBus()
                self._lifecycle = RuntimeLifecycle.PRE_INITIALIZED

            @property
            def clock(self) -> SimulatedClock:
                return self._clock

            @property
            def event_bus(self) -> SimpleEventBus:
                return self._bus

            @property
            def lifecycle(self) -> RuntimeLifecycle:
                return self._lifecycle

            @property
            def state(self) -> RuntimeSnapshot:
                return RuntimeSnapshot(
                    state=self._lifecycle,
                    mode="backtest",
                )

            def transition_to(self, target: RuntimeLifecycle) -> None:
                validate_transition(self._lifecycle, target)
                self._lifecycle = target

        assert isinstance(FakeKernel(), TradingRuntimeKernel)
