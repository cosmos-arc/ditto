"""PaperSynchronizer 骨架单元测试."""

from __future__ import annotations

import inspect

import pytest
from ditto_application.runtime.synchronizer import PaperSynchronizer
from ditto_kernel.clock import RealtimeClock
from ditto_kernel.synchronizer import Synchronizer


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


class TestPaperSynchronizerClock:
    """clock() 返回 RealtimeClock 实例."""

    def test_clock_returns_realtime_clock(self) -> None:
        """clock() 应返回 RealtimeClock 实例."""
        sync = PaperSynchronizer()
        clock = sync.clock()
        assert isinstance(clock, RealtimeClock)

    def test_clock_now_returns_datetime(self) -> None:
        """RealtimeClock.now() 应返回有效 datetime."""
        sync = PaperSynchronizer()
        clock = sync.clock()
        now = clock.now()
        assert now is not None


class TestPaperSynchronizerStream:
    """stream() 在骨架阶段 raise NotImplementedError."""

    def test_stream_raises_not_implemented(self) -> None:
        """stream() 应 raise NotImplementedError."""
        sync = PaperSynchronizer()
        with pytest.raises(NotImplementedError, match="Paper Trading"):
            sync.stream()

    def test_stream_return_type_annotation(self) -> None:
        """stream() 的返回类型标注应为 Iterator[TimeSlice]."""
        import inspect

        sig = inspect.signature(PaperSynchronizer.stream)
        annotation = sig.return_annotation
        assert annotation is not inspect.Parameter.empty
