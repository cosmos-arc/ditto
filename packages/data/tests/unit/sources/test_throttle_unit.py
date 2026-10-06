"""MinIntervalThrottle 单测 — 数据源 client 共享节流器（#516）."""

from __future__ import annotations

import pytest
from ditto_data.sources import throttle as throttle_module
from ditto_data.sources.throttle import MinIntervalThrottle


class TestMinIntervalThrottle:
    def _fake_clock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[dict[str, float], list[float]]:
        clock = {"now": 100.0}
        sleeps: list[float] = []

        def _fake_monotonic() -> float:
            return clock["now"]

        def _fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock["now"] += seconds

        monkeypatch.setattr(throttle_module.time, "monotonic", _fake_monotonic)
        monkeypatch.setattr(throttle_module.time, "sleep", _fake_sleep)
        return clock, sleeps

    def test_first_wait_does_not_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """首个请求无间隔要求."""
        _clock, sleeps = self._fake_clock(monkeypatch)
        throttle = MinIntervalThrottle(0.5)

        throttle.wait()

        assert sleeps == []

    def test_spaces_request_starts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """相邻请求起点间隔不足时补满（mock 时钟）."""
        clock, sleeps = self._fake_clock(monkeypatch)
        throttle = MinIntervalThrottle(0.5)

        throttle.wait()
        clock["now"] += 0.1  # 只过了 0.1s
        throttle.wait()  # 需补 0.4s

        assert sleeps == [pytest.approx(0.4)]

    def test_zero_interval_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """min_interval=0 显式禁用，从不阻塞."""
        _clock, sleeps = self._fake_clock(monkeypatch)
        throttle = MinIntervalThrottle(0.0)

        throttle.wait()
        throttle.wait()

        assert sleeps == []

    def test_negative_interval_clamped_to_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """负间隔钳到 0（禁用），不回绕成永久等待."""
        _clock, sleeps = self._fake_clock(monkeypatch)

        MinIntervalThrottle(-1.0).wait()

        assert sleeps == []

    def test_runtime_raise_takes_effect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """min_interval 可运行时上调（fuyao 限流自适应路径依赖此行为）."""
        clock, sleeps = self._fake_clock(monkeypatch)
        throttle = MinIntervalThrottle(0.1)

        throttle.wait()
        clock["now"] += 0.15
        throttle.wait()  # 间隔已满，不睡
        throttle.min_interval = 0.4  # 限流后上调
        throttle.wait()  # 距上次起点 0s（mock 时钟）→ 需补 0.4s

        assert sleeps == [pytest.approx(0.4)]
