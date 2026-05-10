"""ditto_kernel.synchronizer 单元测试."""

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from datetime import date, datetime

import pytest
from ditto_kernel.clock import Clock, SimulatedClock
from ditto_kernel.identity import InstrumentId
from ditto_kernel.synchronizer import Synchronizer, TimeSlice
from ditto_kernel.time_context import TimeContext
from ditto_kernel.trading import MarketSnapshot


def _make_snapshot(instrument_id: int = 1) -> MarketSnapshot:
    """创建测试用 MarketSnapshot."""
    return MarketSnapshot(
        trade_date="2024-06-15",
        instrument_id=InstrumentId(instrument_id),
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        prev_close=10.0,
        volume=1000000.0,
        amount=10500000.0,
    )


class TestTimeSliceConstruction:
    """TimeSlice 构造测试."""

    def test_basic_construction(self) -> None:
        """应正确构造 TimeSlice."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        bars = {InstrumentId(1): _make_snapshot(1)}
        ts = TimeSlice(time_context=tc, bars=bars)
        assert ts.time_context is tc
        assert ts.bars == bars

    def test_empty_bars(self) -> None:
        """bars 可以是空字典."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        ts = TimeSlice(time_context=tc, bars={})
        assert ts.bars == {}


class TestTimeSliceFrozen:
    """TimeSlice frozen 语义测试."""

    def test_frozen_prevents_attribute_assignment(self) -> None:
        """frozen dataclass 不允许修改属性."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        ts = TimeSlice(time_context=tc, bars={})
        new_tc = TimeContext(
            decision_time=datetime(2024, 6, 16, 15, 0),
            knowledge_date=date(2024, 6, 15),
            trade_date="2024-06-16",
        )
        with pytest.raises(FrozenInstanceError):
            ts.time_context = new_tc  # type: ignore[misc]


class TestTimeSliceEquality:
    """TimeSlice 值相等性测试."""

    def test_equal_instances_are_equal(self) -> None:
        """相同字段值的 TimeSlice 应相等."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        bars = {InstrumentId(1): _make_snapshot(1)}
        ts1 = TimeSlice(time_context=tc, bars=bars)
        ts2 = TimeSlice(time_context=tc, bars=bars)
        assert ts1 == ts2

    def test_not_hashable_due_to_dict_bars(self) -> None:
        """包含 dict 的 frozen dataclass 不可哈希."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        ts = TimeSlice(time_context=tc, bars={})
        with pytest.raises(TypeError, match="unhashable"):
            hash(ts)


class TestSynchronizerProtocol:
    """Synchronizer Protocol 结构化子类型测试."""

    def test_concrete_satisfies_protocol(self) -> None:
        """实现 stream() + clock() 的类应满足 Synchronizer Protocol."""

        class FakeSynchronizer:
            def __init__(self) -> None:
                self._clock = SimulatedClock(datetime(2024, 1, 1))

            def stream(self) -> Iterator[TimeSlice]:
                return iter([])

            def clock(self) -> Clock:
                return self._clock

        sync: Synchronizer = FakeSynchronizer()
        assert isinstance(sync.clock(), SimulatedClock)
        assert list(sync.stream()) == []

    def test_stream_returns_iterator(self) -> None:
        """stream() 应返回 Iterator[TimeSlice]."""

        class FakeSynchronizer:
            def __init__(self) -> None:
                self._clock = SimulatedClock(datetime(2024, 1, 1))

            def stream(self) -> Iterator[TimeSlice]:
                tc = TimeContext(
                    decision_time=datetime(2024, 6, 15, 15, 0),
                    knowledge_date=date(2024, 6, 14),
                    trade_date="2024-06-15",
                )
                yield TimeSlice(time_context=tc, bars={})

            def clock(self) -> Clock:
                return self._clock

        sync: Synchronizer = FakeSynchronizer()
        slices = list(sync.stream())
        assert len(slices) == 1
        assert isinstance(slices[0], TimeSlice)
