"""Pytest fixtures for runtime tests.

提供虚拟时间控制，替代真实的 time.sleep()。
"""

from collections.abc import Generator

import pytest
import time_machine


@pytest.fixture
def frozen_time(
    time_machine: time_machine.TimeMachineFixture,
) -> Generator[time_machine.TimeMachineFixture, None, None]:
    """提供完全控制的虚拟时间（替代真实 sleep）.

    使用方式:
        def test_cache_expires(frozen_time):
            cache.set("key", "value", ttl=2)
            frozen_time.move_to(2)  # 虚拟前进 2 秒
            assert cache.get("key") is None
    """
    import time_machine as tm

    with tm.travel(0, tick=True):
        yield time_machine
