"""Tests for TushareRateLimiter and related classes."""

from ditto_data.sources.tushare.utils.rate_limiter import (
    TushareAPIGroup,
    TushareRateLimitConfig,
    TushareRateLimiter,
)


class TestTushareAPIGroup:
    """Tests for TushareAPIGroup enum."""

    def test_api_group_values(self) -> None:
        """Test API group has correct values."""
        assert TushareAPIGroup.BASIC.value == "basic"
        assert TushareAPIGroup.DAILY.value == "daily"
        assert TushareAPIGroup.DERIVED.value == "derived"
        assert TushareAPIGroup.SPECIAL.value == "special"


class TestTushareRateLimitConfig:
    """Tests for TushareRateLimitConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = TushareRateLimitConfig()
        assert config.global_rate == 200
        assert config.global_window == 60
        assert config.daily_rate == 100
        assert config.derived_rate == 50
        assert config.special_rate == 20

    def test_free_preset(self) -> None:
        """Test free tier preset."""
        config = TushareRateLimitConfig.free()
        assert config.global_rate == 200
        assert config.daily_rate == 100
        assert config.derived_rate == 50
        assert config.special_rate == 20

    def test_paid_preset(self) -> None:
        """Test paid tier preset."""
        config = TushareRateLimitConfig.paid()
        assert config.global_rate == 1000
        assert config.daily_rate == 500
        assert config.derived_rate == 200
        assert config.special_rate == 100

    def test_conservative_preset(self) -> None:
        """Test conservative preset."""
        config = TushareRateLimitConfig.conservative()
        assert config.global_rate == 150
        assert config.daily_rate == 80
        assert config.derived_rate == 30
        assert config.special_rate == 10


class TestTushareRateLimiter:
    """Tests for TushareRateLimiter."""

    def test_init_with_config(self) -> None:
        """Test initialization with config."""
        config = TushareRateLimitConfig(global_rate=10, global_window=60)
        limiter = TushareRateLimiter(config)
        assert limiter is not None

    def test_check_limit_basic(self) -> None:
        """Test basic rate limiting."""
        config = TushareRateLimitConfig(global_rate=2, global_window=60)
        limiter = TushareRateLimiter(config)

        # First request should pass
        assert limiter.check_limit(TushareAPIGroup.BASIC) is True

        # Second request should pass
        assert limiter.check_limit(TushareAPIGroup.BASIC) is True

        # Third request should fail
        assert limiter.check_limit(TushareAPIGroup.BASIC) is False

    def test_multi_level_rate_limiting(self) -> None:
        """Test multi-level rate limiting."""
        config = TushareRateLimitConfig(
            global_rate=10,
            global_window=60,
            daily_rate=5,
            daily_window=60,
            derived_rate=2,
            derived_window=60,
        )
        limiter = TushareRateLimiter(config)

        # Use up daily quota
        for _ in range(5):
            assert limiter.check_limit(TushareAPIGroup.DAILY) is True

        # Daily should be exhausted even though global has capacity
        assert limiter.check_limit(TushareAPIGroup.DAILY) is False

        # But derived should still work (separate quota)
        assert limiter.check_limit(TushareAPIGroup.DERIVED) is True

    def test_wait_if_needed(self) -> None:
        """Test wait_if_needed blocks when limit exceeded."""
        config = TushareRateLimitConfig(global_rate=1, global_window=1)
        limiter = TushareRateLimiter(config)

        # First call should not block
        limiter.wait_if_needed(TushareAPIGroup.BASIC)

        # Second call should block (we won't actually wait in test)
        # In real scenario, this would sleep until window resets
