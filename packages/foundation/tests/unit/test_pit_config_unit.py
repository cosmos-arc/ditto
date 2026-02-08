"""Tests for PIT configuration."""

import os

import pytest
from ditto_foundation.pit import PitConfig, PitStrategy, WindowClosed


class TestWindowClosed:
    """Tests for WindowClosed enum."""

    def test_left_is_safe(self):
        """Test that LEFT is PIT-safe."""
        assert WindowClosed.LEFT.value == "left"

    def test_values(self):
        """Test all enum values."""
        assert WindowClosed.LEFT.value == "left"
        assert WindowClosed.RIGHT.value == "right"
        assert WindowClosed.BOTH.value == "both"
        assert WindowClosed.NONE.value == "none"


class TestPitStrategy:
    """Tests for PitStrategy enum."""

    def test_strict_is_default(self):
        """Test that STRICT is the safest default."""
        assert PitStrategy.STRICT.value == "strict"

    def test_values(self):
        """Test all enum values."""
        assert PitStrategy.STRICT.value == "strict"
        assert PitStrategy.LOOSE.value == "loose"
        assert PitStrategy.LATEST.value == "latest"


class TestPitConfig:
    """Tests for PitConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PitConfig()
        assert config.strategy == PitStrategy.STRICT
        assert config.window_closed == WindowClosed.LEFT
        assert config.knowledge_date_tolerance_days == 0
        assert config.enforce_effective_dates is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PitConfig(
            strategy=PitStrategy.LOOSE,
            window_closed=WindowClosed.LEFT,
            knowledge_date_tolerance_days=3,
        )
        assert config.strategy == PitStrategy.LOOSE
        assert config.knowledge_date_tolerance_days == 3

    def test_from_env_defaults(self):
        """Test from_env with default environment."""
        # Clear env vars
        for key in [
            "DITTO_PIT_STRATEGY",
            "DITTO_PIT_WINDOW_CLOSED",
            "DITTO_PIT_TOLERANCE_DAYS",
        ]:
            os.environ.pop(key, None)

        config = PitConfig.from_env()
        assert config.strategy == PitStrategy.STRICT
        assert config.window_closed == WindowClosed.LEFT
        assert config.knowledge_date_tolerance_days == 0

    def test_from_env_custom(self):
        """Test from_env with custom environment variables."""
        os.environ["DITTO_PIT_STRATEGY"] = "loose"
        os.environ["DITTO_PIT_WINDOW_CLOSED"] = "left"
        os.environ["DITTO_PIT_TOLERANCE_DAYS"] = "5"

        config = PitConfig.from_env()
        assert config.strategy == PitStrategy.LOOSE
        assert config.window_closed == WindowClosed.LEFT
        assert config.knowledge_date_tolerance_days == 5

        # Cleanup
        for key in [
            "DITTO_PIT_STRATEGY",
            "DITTO_PIT_WINDOW_CLOSED",
            "DITTO_PIT_TOLERANCE_DAYS",
        ]:
            os.environ.pop(key, None)

    def test_from_env_invalid_strategy(self):
        """Test from_env with invalid strategy (should fallback to STRICT)."""
        os.environ["DITTO_PIT_STRATEGY"] = "invalid"
        os.environ.pop("DITTO_PIT_WINDOW_CLOSED", None)
        os.environ.pop("DITTO_PIT_TOLERANCE_DAYS", None)

        config = PitConfig.from_env()
        assert config.strategy == PitStrategy.STRICT

        # Cleanup
        os.environ.pop("DITTO_PIT_STRATEGY", None)

    def test_from_env_invalid_window_closed(self):
        """Test from_env with invalid window_closed (should fallback to LEFT)."""
        os.environ.pop("DITTO_PIT_STRATEGY", None)
        os.environ["DITTO_PIT_WINDOW_CLOSED"] = "invalid"
        os.environ.pop("DITTO_PIT_TOLERANCE_DAYS", None)

        config = PitConfig.from_env()
        assert config.window_closed == WindowClosed.LEFT

        # Cleanup
        os.environ.pop("DITTO_PIT_WINDOW_CLOSED", None)

    def test_from_env_invalid_tolerance(self):
        """Test from_env with invalid tolerance (should fallback to 0)."""
        os.environ.pop("DITTO_PIT_STRATEGY", None)
        os.environ.pop("DITTO_PIT_WINDOW_CLOSED", None)
        os.environ["DITTO_PIT_TOLERANCE_DAYS"] = "invalid"

        config = PitConfig.from_env()
        assert config.knowledge_date_tolerance_days == 0

        # Cleanup
        os.environ.pop("DITTO_PIT_TOLERANCE_DAYS", None)

    def test_validate_for_safety_default(self):
        """Test validate_for_safety with default (safe) config."""
        config = PitConfig()
        config.validate_for_safety()  # Should not raise

    def test_validate_for_safety_unsafe_window(self):
        """Test validate_for_safety with unsafe window_closed."""
        config = PitConfig(window_closed=WindowClosed.RIGHT)
        with pytest.raises(ValueError, match="Unsafe PIT configuration"):
            config.validate_for_safety()

    def test_validate_for_safety_unsafe_strategy(self):
        """Test validate_for_safety with unsafe strategy."""
        config = PitConfig(strategy=PitStrategy.LATEST)
        with pytest.raises(ValueError, match="Unsafe PIT configuration"):
            config.validate_for_safety()

    def test_frozen(self):
        """Test that PitConfig is frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        config = PitConfig()
        with pytest.raises(FrozenInstanceError):
            config.strategy = PitStrategy.LOOSE
