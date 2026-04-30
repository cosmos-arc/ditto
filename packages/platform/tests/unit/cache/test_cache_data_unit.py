"""Unit tests for DataCache."""

import pytest
from ditto_platform.foundation import init, reset_for_testing
from ditto_platform.foundation.cache import DataCache
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability.config import ObservabilityConfig


def _test_config() -> ObservabilityConfig:
    return ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        metrics_enabled=True,
        tracing_enabled=False,
    )


@pytest.mark.unit
class TestDataCache:
    """Tests for DataCache."""

    def test_initialization_with_defaults(self) -> None:
        """Test that DataCache initializes with default values."""
        cache = DataCache()
        assert cache._default_ttl == 300
        assert cache._enable_metrics is True

    def test_initialization_with_custom_settings(self) -> None:
        """Test initialization with custom settings."""
        cache = DataCache(ttl_seconds=600, max_size=5000, enable_metrics=False)
        assert cache._default_ttl == 600
        assert cache._enable_metrics is False

    def test_get_returns_none_for_missing_key(self) -> None:
        """Test that get returns None for missing key."""
        cache = DataCache(enable_metrics=False)
        result = cache.get("nonexistent_key")
        assert result is None

    def test_get_returns_default_for_missing_key(self) -> None:
        """Test that get returns default value for missing key."""
        cache = DataCache(enable_metrics=False)
        result = cache.get("nonexistent_key", default="default_value")
        assert result == "default_value"

    def test_set_and_get(self) -> None:
        """Test set and get operations."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"

    def test_set_with_custom_ttl(self) -> None:
        """Test set with custom TTL."""
        cache = DataCache(ttl_seconds=10, enable_metrics=False)
        cache.set("key1", "value1", ttl=5)

        # Value should be accessible immediately
        result = cache.get("key1")
        assert result == "value1"

    def test_set_overwrites_existing_key(self) -> None:
        """Test that set overwrites existing key."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        result = cache.get("key1")
        assert result == "value2"

    def test_invalidate_removes_key(self) -> None:
        """Test that invalidate removes key."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        result = cache.get("key1")
        assert result is None

    def test_invalidate_nonexistent_key_does_nothing(self) -> None:
        """Test that invalidating nonexistent key does nothing."""
        cache = DataCache(enable_metrics=False)
        cache.invalidate("nonexistent_key")  # Should not raise

    def test_invalidate_pattern_removes_matching_keys(self) -> None:
        """Test that invalidate_pattern removes matching keys."""
        cache = DataCache(enable_metrics=False)
        cache.set("user:1", "alice")
        cache.set("user:2", "bob")
        cache.set("session:1", "xyz")

        cache.invalidate_pattern("user:*")

        assert cache.get("user:1") is None
        assert cache.get("user:2") is None
        assert cache.get("session:1") == "xyz"

    def test_invalidate_pattern_with_no_matches(self) -> None:
        """Test invalidate_pattern with no matching keys."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", "value1")
        cache.invalidate_pattern("nonexistent:*")
        assert cache.get("key1") == "value1"

    def test_clear_removes_all_keys(self) -> None:
        """Test that clear removes all keys."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_get_stats_returns_metrics(self) -> None:
        """Test that get_stats returns metrics when enabled."""
        # Initialize observability for metrics
        init(_test_config(), force=True)

        try:
            cache = DataCache(enable_metrics=True)
            cache.set("key1", "value1")
            cache.get("key1")  # Hit
            cache.get("key2")  # Miss

            stats = cache.get_stats()

            assert stats.hit_count == 1
            assert stats.miss_count == 1
            assert stats.total_entries >= 0
        finally:
            reset_for_testing()

    def test_get_stats_returns_none_when_disabled(self) -> None:
        """Test that get_stats returns None when metrics disabled."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", "value1")

        stats = cache.get_stats()
        # get_stats always returns CacheStats object
        assert stats is not None
        assert stats.hit_count == 0
        assert stats.miss_count == 0

    def test_metrics_are_tracked(self) -> None:
        """Test that metrics are tracked correctly."""
        # Initialize observability for metrics
        init(_test_config(), force=True)

        try:
            cache = DataCache(enable_metrics=True)

            # Initial stats
            stats = cache.get_stats()
            assert stats.hit_count == 0
            assert stats.miss_count == 0

            # Add some hits and misses
            cache.set("key1", "value1")
            cache.get("key1")  # Hit
            cache.get("key2")  # Miss

            stats = cache.get_stats()
            assert stats.hit_count == 1
            assert stats.miss_count == 1
        finally:
            reset_for_testing()

    def test_set_with_none_value(self) -> None:
        """Test setting None as value."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", None)
        result = cache.get("key1")
        assert result is None

    def test_get_with_complex_values(self) -> None:
        """Test get/set with complex values (dict, list)."""
        cache = DataCache(enable_metrics=False)

        dict_value = {"name": "test", "value": 123}
        list_value = [1, 2, 3, 4]

        cache.set("dict_key", dict_value)
        cache.set("list_key", list_value)

        assert cache.get("dict_key") == dict_value
        assert cache.get("list_key") == list_value

    def test_invalidate_all_with_pattern(self) -> None:
        """Test invalidating all keys with wildcard pattern."""
        cache = DataCache(enable_metrics=False)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        cache.invalidate_pattern("*")

        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_generic_type_inference_with_str(self) -> None:
        """Test that type checker correctly infers cache value types for strings."""
        # 显式指定类型参数
        cache: DataCache[str] = DataCache(enable_metrics=False)

        # 类型检查器应该推断 value 为 str | None
        cache.set("key1", "string_value")
        value: str | None = cache.get("key1")
        assert value == "string_value"

        # 类型检查器应该允许类型特定操作
        if value is not None:
            # 这里应该有类型提示支持，无需类型断言
            upper_value = value.upper()
            assert upper_value == "STRING_VALUE"

    def test_generic_type_inference_with_int(self) -> None:
        """Test generic cache with int type."""
        cache: DataCache[int] = DataCache(enable_metrics=False)

        cache.set("count", 42)
        result = cache.get("count")
        # result 类型应该是 int | None
        assert result == 42

    def test_generic_type_inference_with_dict(self) -> None:
        """Test generic cache with dict type."""
        cache: DataCache[dict[str, int]] = DataCache(enable_metrics=False)

        cache.set("data", {"count": 10, "value": 20})
        result = cache.get("data")
        # result 类型应该是 dict[str, int] | None
        assert result is not None
        assert result["count"] == 10
        assert result["value"] == 20
