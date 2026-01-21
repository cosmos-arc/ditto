"""Tests for DataCache."""

from ditto_foundation.cache import CacheStats, DataCache


class TestDataCache:
    """Test cases for DataCache."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # [REVIEW] TTL 和 size 进行测试
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

        # [REVIEW] sid: 开头的键
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
        import time

        # 使用短 TTL 加速测试（cachebox C 扩展不受 time_machine 控制）
        self.cache._cache.insert("key1", "value1", ttl=0.05)  # 50ms TTL

        # [REVIEW]
        assert self.cache.get("key1") == "value1"

        # [REVIEW] TTL 过期(50ms + buffer) - 真实等待
        time.sleep(0.06)

        # [REVIEW] None
        assert self.cache.get("key1") is None

    def test_lru_eviction(self) -> None:
        """Test LRU eviction when max_size is exceeded."""
        # max_size = 5
        for i in range(7):
            self.cache.set(f"key{i}", f"value{i}")

        # [REVIEW] 5 个键存在
        assert len(self.cache) <= 5
        assert self.cache.get("key6") is not None
        assert self.cache.get("key5") is not None
        # [REVIEW]
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

        assert stats.total_entries == 1  # [REVIEW] key2
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
        # [REVIEW]
        self.cache.set("trading_days:2024-01", ["2024-01-01", "2024-01-02"])
        self.cache.set("sid:current:tushare:600000.SH", "600000.SH")
        self.cache.set("sid:pit:tushare:600000.SH:2024-06", "600000.SH")

        assert self.cache.get("trading_days:2024-01") is not None
        assert self.cache.get("sid:current:tushare:600000.SH") is not None
        assert self.cache.get("sid:pit:tushare:600000.SH:2024-06") is not None

    def test_set_with_ttl_none_uses_default_ttl(self) -> None:
        """Test set with ttl=None uses default TTL."""
        import time

        # 创建一个短 TTL 的缓存用于测试（cachebox C 扩展不受 time_machine 控制）
        test_cache = DataCache(ttl_seconds=1, max_size=5, enable_metrics=False)
        # 覆盖为短 TTL
        test_cache._default_ttl = 0.05  # 50ms TTL

        # ttl=None 应该使用默认 TTL (50ms)
        test_cache.set("key1", "value1", ttl=None)

        # [REVIEW]
        assert test_cache.get("key1") == "value1"

        # [REVIEW] TTL 过期 - 真实等待
        time.sleep(0.06)

        # [REVIEW] None
        assert test_cache.get("key1") is None

    def test_set_with_ttl_zero_no_expiration(self) -> None:
        """Test set with ttl=0 means no expiration."""
        import time

        # ttl=0 表示永不过期
        self.cache.set("key1", "value1", ttl=0)

        # [REVIEW] TTL - 等待一小段时间验证确实不会过期
        time.sleep(0.06)

        # [REVIEW](因为设置了 ttl=0，永不过期)
        assert self.cache.get("key1") == "value1"

    def test_set_with_custom_ttl(self) -> None:
        """Test set with custom TTL value."""
        import time

        # 使用短 TTL 加速测试（cachebox C 扩展不受 time_machine 控制）
        # [REVIEW] TTL 为 100ms
        self.cache.set("key1", "value1", ttl=0.1)

        # [REVIEW]
        assert self.cache.get("key1") == "value1"

        # [REVIEW] 50ms，应该还在
        time.sleep(0.05)
        assert self.cache.get("key1") == "value1"

        # [REVIEW] 再等 60ms（总共 110ms），应该过期
        time.sleep(0.06)
        assert self.cache.get("key1") is None


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
        assert stats.total_entries == 1  # [REVIEW] key2
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

    def test_invalidate_pattern_with_metrics(self) -> None:
        """Test invalidate_pattern with metrics enabled records metrics."""
        self.cache.set("sid:600000.SH", "value1")
        self.cache.set("sid:600000.SH:2024-01", "value2")

        # [REVIEW] sid: 开头的键 - 这会触发 line 168 的 M.cache_invalidations.add(1)
        count = self.cache.invalidate_pattern("sid:*")

        assert count == 2
        stats = self.cache.get_stats()
        assert stats.invalidation_count == 2
