"""DataCache TTL 条目级别支持的测试."""

import time

import pytest
from ditto_platform.foundation.cache import DataCache


def test_individual_ttl(frozen_time) -> None:
    """测试单条目 TTL 功能."""
    cache = DataCache(ttl_seconds=300)

    cache.set("key1", "value1", ttl=0.05)  # 0.05 秒过期
    cache.set("key2", "value2")  # 使用默认 TTL 300 秒

    # 验证初始状态
    assert cache.get("key1") == "value1"
    assert cache.get("key2") == "value2"

    # 等待 0.1 秒（真实等待，但时间很短）
    time.sleep(0.1)

    # key1 应该已过期（0.05 秒 TTL）
    assert cache.get("key1") is None

    # key2 仍然有效（300 秒 TTL）
    assert cache.get("key2") == "value2"


def test_individual_ttl_with_zero():
    """测试 TTL 为 0 的情况."""
    cache = DataCache(ttl_seconds=300)

    # cachebox 允许零 TTL(表示永不过期)
    cache.set("key1", "value1", ttl=0)
    assert cache.get("key1") == "value1"


def test_individual_ttl_with_negative():
    """测试 TTL 为负数的情况应该抛出异常."""
    cache = DataCache(ttl_seconds=300)

    # cachebox 不允许负 TTL
    with pytest.raises(ValueError, match="ttl must be positive and non-zero"):
        cache.set("key1", "value1", ttl=-1)


def test_individual_ttl_none_value(frozen_time) -> None:
    """测试 ttl=None 时使用默认 TTL."""
    cache = DataCache(ttl_seconds=300)

    cache.set("key1", "value1")  # 使用默认 TTL (300 秒)
    cache.set("key2", "value2", ttl=0.05)  # 0.05 秒过期

    # 验证初始状态
    assert cache.get("key1") == "value1"
    assert cache.get("key2") == "value2"

    # 等待 0.1 秒
    time.sleep(0.1)

    # key1 仍然有效(使用默认 TTL 300 秒)
    assert cache.get("key1") == "value1"

    # key2 已过期(0.05 秒 TTL)
    assert cache.get("key2") is None


def test_individual_ttl_get_stats(frozen_time) -> None:
    """测试统计功能在 TTL 场景下的正确性."""
    cache = DataCache(ttl_seconds=300)

    # 设置两个键，TTL 为 0.05 秒
    cache.set("key1", "value1", ttl=0.05)
    cache.set("key2", "value2", ttl=0.05)

    # 初始读取应该命中
    assert cache.get("key1") == "value1"
    assert cache.get("key2") == "value2"

    # 验证初始统计（应该命中）
    stats = cache.get_stats()
    assert stats.hit_count >= 2
    assert stats.miss_count == 0

    # 等待 0.1 秒
    time.sleep(0.1)

    # 键已过期，应该未命中
    assert cache.get("key1") is None
    assert cache.get("key2") is None

    # 验证最终统计
    stats = cache.get_stats()
    assert stats.hit_count >= 2
    assert stats.miss_count >= 2
