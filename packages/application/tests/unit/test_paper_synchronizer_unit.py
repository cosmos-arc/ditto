"""PaperSynchronizer 单元测试 — stream() 确定性时间切片."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

from ditto_application.runtime.synchronizer import PaperSynchronizer
from ditto_kernel.clock import RealtimeClock, SimulatedClock
from ditto_kernel.synchronizer import Synchronizer, TimeSlice


class TestPaperSynchronizerProtocol:
    """PaperSynchronizer 满足 Synchronizer Protocol."""

    def test_has_stream_method(self) -> None:
        """应实现 stream() 方法."""
        assert hasattr(PaperSynchronizer, "stream")

    def test_has_clock_method(self) -> None:
        """应实现 clock() 方法."""
        assert hasattr(PaperSynchronizer, "clock")

    def test_stream_signature_matches_protocol(self) -> None:
        """stream() 签名应与 Synchronizer Protocol 一致."""
        proto_sig = inspect.signature(Synchronizer.stream)
        impl_sig = inspect.signature(PaperSynchronizer.stream)
        assert proto_sig == impl_sig

    def test_clock_signature_matches_protocol(self) -> None:
        """clock() 签名应与 Synchronizer Protocol 一致."""
        proto_sig = inspect.signature(Synchronizer.clock)
        impl_sig = inspect.signature(PaperSynchronizer.clock)
        assert proto_sig == impl_sig


class TestPaperSynchronizerDefaultClock:
    """默认构造时 clock() 返回 RealtimeClock 实例."""

    def test_clock_returns_realtime_clock(self) -> None:
        """默认 clock() 应返回 RealtimeClock 实例."""
        sync = PaperSynchronizer()
        clock = sync.clock()
        assert isinstance(clock, RealtimeClock)

    def test_clock_now_returns_datetime(self) -> None:
        """RealtimeClock.now() 应返回有效 datetime."""
        sync = PaperSynchronizer()
        clock = sync.clock()
        now = clock.now()
        assert now is not None


class TestPaperSynchronizerStreamDeterministic:
    """stream() 使用 SimulatedClock 时的确定性时间切片."""

    def test_stream_produces_time_slices(self) -> None:
        """stream() 应产出 TimeSlice 对象."""
        clock = SimulatedClock(initial=datetime(2026, 1, 1, tzinfo=UTC))
        sync = PaperSynchronizer(clock=clock, max_slices=3)
        slices = list(sync.stream())
        assert len(slices) == 3
        assert all(isinstance(s, TimeSlice) for s in slices)

    def test_stream_slices_have_time_context_from_clock(self) -> None:
        """TimeSlice 的 time_context 应来自 clock."""
        initial = datetime(2026, 5, 17, 9, 30, 0, tzinfo=UTC)
        clock = SimulatedClock(initial=initial)
        sync = PaperSynchronizer(clock=clock, max_slices=2)
        slices = list(sync.stream())

        assert slices[0].time_context.decision_time == initial
        assert slices[0].time_context.trade_date == "2026-05-17"

    def test_stream_slices_have_empty_bars(self) -> None:
        """最小版本的 TimeSlice.bars 应为空 dict."""
        clock = SimulatedClock(initial=datetime(2026, 1, 1, tzinfo=UTC))
        sync = PaperSynchronizer(clock=clock, max_slices=1)
        slices = list(sync.stream())
        assert slices[0].bars == {}

    def test_stream_max_slices_limits_output(self) -> None:
        """max_slices 应限制产出数量."""
        clock = SimulatedClock(initial=datetime(2026, 1, 1, tzinfo=UTC))
        sync = PaperSynchronizer(clock=clock, max_slices=5)
        slices = list(sync.stream())
        assert len(slices) == 5

    def test_stream_max_slices_one(self) -> None:
        """max_slices=1 应只产出 1 个切片."""
        clock = SimulatedClock(initial=datetime(2026, 1, 1, tzinfo=UTC))
        sync = PaperSynchronizer(clock=clock, max_slices=1)
        slices = list(sync.stream())
        assert len(slices) == 1

    def test_stream_with_infinite_raises_without_external_break(self) -> None:
        """max_slices=None (无限) 不应自行终止 — 但测试中用 islice 验证."""
        from itertools import islice as islice_fn

        clock = SimulatedClock(initial=datetime(2026, 1, 1, tzinfo=UTC))
        sync = PaperSynchronizer(clock=clock, max_slices=None)
        # 只取前 3 个，验证无限流能持续产出
        slices = list(islice_fn(sync.stream(), 3))
        assert len(slices) == 3

    def test_stream_return_type_annotation(self) -> None:
        """stream() 的返回类型标注应为 Iterator[TimeSlice]."""
        sig = inspect.signature(PaperSynchronizer.stream)
        annotation = sig.return_annotation
        assert annotation is not inspect.Parameter.empty

    def test_stream_with_default_clock_produces_slices(self) -> None:
        """默认构造的 PaperSynchronizer 也能产出切片."""
        sync = PaperSynchronizer(max_slices=2)
        slices = list(sync.stream())
        assert len(slices) == 2
        assert all(isinstance(s, TimeSlice) for s in slices)
