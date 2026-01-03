"""测试 fake_time fixture 的功能."""

import time


def test_fake_time_sleep_is_instant(fake_time: None) -> None:
    """测试 fake_time 使 sleep 立即完成（真实时间接近 0）."""
    # 使用 perf_counter 测量真实经过时间
    start = time.perf_counter()
    time.sleep(10)
    end = time.perf_counter()

    # fake_time 使 sleep 立即完成，真实时间差应该接近 0
    assert end - start < 0.1


def test_fake_time_time_advances(fake_time: None) -> None:
    """测试 fake_time 使 time.time 按预期前进."""
    before = time.time()
    time.sleep(5)
    after = time.time()

    # time.time 应该前进了 5 秒
    assert after - before == 5.0


def test_fake_time_multiple_sleeps(fake_time: None) -> None:
    """测试多次 sleep 累积时间."""
    before = time.time()
    time.sleep(1)
    time.sleep(2)
    time.sleep(3)
    after = time.time()

    # 总共应该前进了 6 秒
    assert after - before == 6.0
