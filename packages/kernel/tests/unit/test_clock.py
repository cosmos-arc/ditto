"""ditto_kernel.clock 单元测试."""

from datetime import date, datetime

import pytest
from ditto_kernel.clock import Clock, RealtimeClock, SimulatedClock


class TestSimulatedClock:
    """SimulatedClock 测试."""

    def test_initial_time(self) -> None:
        """初始时间应为构造参数."""
        clock = SimulatedClock(datetime(2024, 1, 15, 9, 30))
        assert clock.now() == datetime(2024, 1, 15, 9, 30)

    def test_today(self) -> None:
        """today 应返回日期部分."""
        clock = SimulatedClock(datetime(2024, 1, 15, 9, 30))
        assert clock.today() == date(2024, 1, 15)

    def test_advance_to(self) -> None:
        """advance_to 应推进时间."""
        clock = SimulatedClock(datetime(2024, 1, 1))
        target = datetime(2024, 6, 15, 15, 0)
        clock.advance_to(target)
        assert clock.now() == target

    def test_advance_to_rejects_backward(self) -> None:
        """advance_to 不允许时间回退."""
        clock = SimulatedClock(datetime(2024, 6, 1))
        with pytest.raises(ValueError, match="不能回退"):
            clock.advance_to(datetime(2024, 1, 1))

    def test_advance_to_same_time_is_noop(self) -> None:
        """advance_to 同一时间应为空操作."""
        ts = datetime(2024, 3, 15, 10, 0)
        clock = SimulatedClock(ts)
        clock.advance_to(ts)
        assert clock.now() == ts


class TestRealtimeClock:
    """RealtimeClock 测试."""

    def test_now_returns_datetime(self) -> None:
        """now 应返回当前时间."""
        clock = RealtimeClock()
        result = clock.now()
        assert isinstance(result, datetime)

    def test_today_returns_date(self) -> None:
        """today 应返回当前日期."""
        clock = RealtimeClock()
        result = clock.today()
        assert isinstance(result, date)
        assert result == date.today()

    def test_advance_to_raises(self) -> None:
        """advance_to 应抛出 RuntimeError."""
        clock = RealtimeClock()
        with pytest.raises(RuntimeError, match="实时时钟"):
            clock.advance_to(datetime(2024, 1, 1))


class TestClockProtocol:
    """Clock Protocol 一致性测试."""

    def test_simulated_clock_satisfies_protocol(self) -> None:
        """SimulatedClock 应满足 Clock Protocol."""
        clock: Clock = SimulatedClock(datetime(2024, 1, 1))
        assert clock.now() == datetime(2024, 1, 1)

    def test_realtime_clock_satisfies_protocol(self) -> None:
        """RealtimeClock 应满足 Clock Protocol."""
        clock: Clock = RealtimeClock()
        assert isinstance(clock.now(), datetime)
