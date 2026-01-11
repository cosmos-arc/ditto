"""Pytest configuration for datahub tests."""

from collections.abc import Generator

import pytest
from ditto_foundation import Mode, init


@pytest.fixture(autouse=True)
def init_observability() -> None:
    """Initialize observability in testing mode for all tests."""
    init(mode=Mode.TESTING)
    # Cleanup is handled by reset_for_testing if needed


@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """可控的时间 fixture，通过 monkeypatch 替换时间函数.

    使 time.sleep 立即完成，time.time 按预期前进，提高测试速度和确定性。
    """
    current_time = [0.0]

    def fake_sleep(seconds: float) -> None:
        current_time[0] += seconds

    def fake_time_func() -> float:
        return current_time[0]

    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("time.time", fake_time_func)

    return
