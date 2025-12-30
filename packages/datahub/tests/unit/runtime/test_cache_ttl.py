"""DataCache TTL 条目级别支持的测试."""

import time

import pytest
from ditto_datahub.runtime.cache import DataCache


def test_individual_ttl():
    """测试单条目 TTL 功能."""
    cache = DataCache(ttl_seconds=300)

    cache.set("key1", "value1", ttl=2)  # 2 秒过期
    cache.set("key2", "value2")  # 使用默认 300 秒

    time.sleep(3)

    # key1 应该已过期
    assert cache.get("key1") is None

    # key2 仍然有效
    assert cache.get("key2") == "value2"


def test_individual_ttl_with_zero():
    """测试 TTL 为 0 的情况应该抛出异常."""
    cache = DataCache(ttl_seconds=300)

    # VTTLCache 不允许零 TTL
    with pytest.raises(ValueError, match="ttl must be positive and non-zero"):
        cache.set("key1", "value1", ttl=0)


def test_individual_ttl_with_negative():
    """测试 TTL 为负数的情况应该抛出异常."""
    cache = DataCache(ttl_seconds=300)

    # VTTLCache 不允许负 TTL
    with pytest.raises(ValueError, match="ttl must be positive and non-zero"):
        cache.set("key1", "value1", ttl=-1)


def test_individual_ttl_none_value():
    """测试 ttl=None 时使用默认 TTL."""
    cache = DataCache(ttl_seconds=300)

    cache.set("key1", "value1")  # 使用默认 TTL
    cache.set("key2", "value2", ttl=2)  # 2 秒过期

    time.sleep(3)

    # key1 仍然有效（使用默认 TTL）
    assert cache.get("key1") == "value1"

    # key2 已过期
    assert cache.get("key2") is None


def test_individual_ttl_get_stats():
    """测试统计功能在 TTL 场景下的正确性."""
    cache = DataCache(ttl_seconds=300)

    # 设置一些值
    cache.set("key1", "value1", ttl=2)
    cache.set("key2", "value2", ttl=2)

    # 获取值（应该命中）
    assert cache.get("key1") == "value1"
    assert cache.get("key2") == "value2"

    # 获取统计信息
    stats = cache.get_stats()
    assert stats.hit_count >= 2
    assert stats.miss_count == 0

    time.sleep(3)

    # 再次获取（应该未命中）
    assert cache.get("key1") is None
    assert cache.get("key2") is None

    # 获取统计信息
    stats = cache.get_stats()
    assert stats.hit_count >= 2
    assert stats.miss_count >= 2
