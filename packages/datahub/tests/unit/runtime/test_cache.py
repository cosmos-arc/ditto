"""Tests for DataCache."""

import time

from ditto_datahub.runtime.cache import CacheStats, DataCache


class TestDataCache:
    """Test cases for DataCache."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # 使用较小的 TTL 和 size 进行测试
        self.cache = DataCache(ttl_seconds=1, max_size=5, enable_metrics=False)

    def test_set_and_get(self) -> None:
        """Test basic set and get operations."""
        self.cache.set("key1", "value1")

        assert self.cache.get("key1") == "value1"
        assert "key1" in self.cache

    def test_get_with_default(self) -> None:
        """Test get returns default value for missing keys."""
        assert self.cache.get("missing") is None
        assert self.cache.get("missing", "default") == "default"

    def test_get_updates_stats(self) -> None:
        """Test get updates hit/miss counters."""
        self.cache.set("key1", "value1")

        # Miss
        self.cache.get("missing")
        stats = self.cache.get_stats()
        assert stats.miss_count == 1
        assert stats.hit_count == 0

        # Hit
        self.cache.get("key1")
        stats = self.cache.get_stats()
        assert stats.hit_count == 1
        assert stats.miss_count == 1

    def test_invalidate_existing_key(self) -> None:
        """Test invalidate removes existing key."""
        self.cache.set("key1", "value1")

        result = self.cache.invalidate("key1")

        assert result is True
        assert self.cache.get("key1") is None
        assert "key1" not in self.cache

    def test_invalidate_non_existing_key(self) -> None:
        """Test invalidate returns False for non-existing keys."""
        result = self.cache.invalidate("missing")

        assert result is False

    def test_invalidate_updates_stats(self) -> None:
        """Test invalidate updates invalidation counter."""
        self.cache.set("key1", "value1")
        self.cache.invalidate("key1")

        stats = self.cache.get_stats()
        assert stats.invalidation_count == 1

    def test_invalidate_pattern(self) -> None:
        """Test invalidate_pattern removes matching keys."""
        self.cache.set("sid:600000.SH", "value1")
        self.cache.set("sid:600000.SH:2024-01", "value2")
        self.cache.set("trading_days:2024-01", "value3")
        self.cache.set("other:key", "value4")

        # 失效所有 sid: 开头的键
        count = self.cache.invalidate_pattern("sid:*")

        assert count == 2
        assert self.cache.get("sid:600000.SH") is None
        assert self.cache.get("sid:600000.SH:2024-01") is None
        assert self.cache.get("trading_days:2024-01") == "value3"
        assert self.cache.get("other:key") == "value4"

    def test_invalidate_pattern_no_matches(self) -> None:
        """Test invalidate_pattern returns 0 when no matches."""
        self.cache.set("key1", "value1")

        count = self.cache.invalidate_pattern("nonexistent:*")

        assert count == 0
        assert self.cache.get("key1") == "value1"

    def test_clear(self) -> None:
        """Test clear removes all entries."""
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")

        self.cache.clear()

        assert len(self.cache) == 0
        assert self.cache.get("key1") is None
        assert self.cache.get("key2") is None

    def test_len(self) -> None:
        """Test __len__ returns correct count."""
        assert len(self.cache) == 0

        self.cache.set("key1", "value1")
        assert len(self.cache) == 1

        self.cache.set("key2", "value2")
        assert len(self.cache) == 2

    def test_contains(self) -> None:
        """Test __contains__ checks key existence."""
        self.cache.set("key1", "value1")

        assert "key1" in self.cache
        assert "key2" not in self.cache

    def test_ttl_expiration(self) -> None:
        """Test entries expire after TTL."""
        self.cache.set("key1", "value1")

        # 立即获取应该成功
        assert self.cache.get("key1") == "value1"

        # 等待 TTL 过期（1 秒 + buffer）
        time.sleep(1.2)

        # 过期后应该返回 None
        assert self.cache.get("key1") is None

    def test_lru_eviction(self) -> None:
        """Test LRU eviction when max_size is exceeded."""
        # max_size = 5
        for i in range(7):
            self.cache.set(f"key{i}", f"value{i}")

        # 只有最新的 5 个键存在
        assert len(self.cache) <= 5
        assert self.cache.get("key6") is not None
        assert self.cache.get("key5") is not None
        # 最早的键应该被淘汰
        assert self.cache.get("key0") is None
        assert self.cache.get("key1") is None

    def test_get_stats(self) -> None:
        """Test get_stats returns correct statistics."""
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")

        # 2 hits, 1 miss
        self.cache.get("key1")
        self.cache.get("key2")
        self.cache.get("missing")

        # 1 invalidation
        self.cache.invalidate("key1")

        stats = self.cache.get_stats()

        assert stats.total_entries == 1  # 只有 key2
        assert stats.hit_count == 2
        assert stats.miss_count == 1
        assert stats.hit_rate == 2 / 3
        assert stats.invalidation_count == 1

    def test_get_stats_empty_cache(self) -> None:
        """Test get_stats handles empty cache."""
        stats = self.cache.get_stats()

        assert stats.total_entries == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0
        assert stats.hit_rate == 0.0

    def test_overwrite_existing_key(self) -> None:
        """Test overwriting existing key updates value."""
        self.cache.set("key1", "value1")
        self.cache.set("key1", "value2")

        assert self.cache.get("key1") == "value2"
        assert len(self.cache) == 1

    def test_cache_key_naming_convention(self) -> None:
        """Test cache follows recommended naming convention."""
        # 测试推荐的命名格式
        self.cache.set("trading_days:2024-01", ["2024-01-01", "2024-01-02"])
        self.cache.set("sid:current:tushare:600000.SH", "600000.SH")
        self.cache.set("sid:pit:tushare:600000.SH:2024-06", "600000.SH")

        assert self.cache.get("trading_days:2024-01") is not None
        assert self.cache.get("sid:current:tushare:600000.SH") is not None
        assert self.cache.get("sid:pit:tushare:600000.SH:2024-06") is not None


class TestCacheStats:
    """Test cases for CacheStats dataclass."""

    def test_cache_stats_creation(self) -> None:
        """Test CacheStats can be created."""
        stats = CacheStats(
            total_entries=10,
            hit_count=80,
            miss_count=20,
            hit_rate=0.8,
            invalidation_count=5,
            evict_count=2,
        )

        assert stats.total_entries == 10
        assert stats.hit_count == 80
        assert stats.miss_count == 20
        assert stats.hit_rate == 0.8
        assert stats.invalidation_count == 5
        assert stats.evict_count == 2


class TestDataCacheWithMetrics:
    """Test cases for DataCache with metrics enabled."""

    def setup_method(self) -> None:
        """Set up test environment with metrics enabled."""
        self.cache = DataCache(ttl_seconds=60, max_size=100, enable_metrics=True)

    def test_get_stats_with_metrics_enabled(self) -> None:
        """Test get_stats returns correct stats when metrics are enabled."""
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")

        # 2 hits, 1 miss
        self.cache.get("key1")
        self.cache.get("key2")
        self.cache.get("missing")

        # 1 invalidation
        self.cache.invalidate("key1")

        stats = self.cache.get_stats()

        # Should have correct counts even in metrics mode
        assert stats.total_entries == 1  # 只有 key2
        assert stats.hit_count == 2
        assert stats.miss_count == 1
        assert stats.hit_rate == 2 / 3
        assert stats.invalidation_count == 1

    def test_get_stats_with_metrics_empty_cache(self) -> None:
        """Test get_stats with metrics enabled on empty cache."""
        stats = self.cache.get_stats()

        assert stats.total_entries == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0
        assert stats.hit_rate == 0.0
        assert stats.invalidation_count == 0
