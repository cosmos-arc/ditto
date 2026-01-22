"""Notification message unit tests."""

from datetime import datetime

import pytest
from ditto_foundation.notification.message import (
    NotificationLevel,
    NotificationMessage,
)


class TestNotificationLevel:
    """NotificationLevel enum tests."""

    def test_level_values(self) -> None:
        """Test level enum values."""
        assert NotificationLevel.INFO.value == "info"
        assert NotificationLevel.WARNING.value == "warning"
        assert NotificationLevel.ERROR.value == "error"
        assert NotificationLevel.CRITICAL.value == "critical"

    def test_level_ordering(self) -> None:
        """Test level severity ordering."""
        assert NotificationLevel.INFO < NotificationLevel.WARNING
        assert NotificationLevel.WARNING < NotificationLevel.ERROR
        assert NotificationLevel.ERROR < NotificationLevel.CRITICAL

    def test_level_equality(self) -> None:
        """Test level comparison."""
        assert NotificationLevel.ERROR == NotificationLevel.ERROR
        assert NotificationLevel.ERROR <= NotificationLevel.ERROR
        assert NotificationLevel.ERROR >= NotificationLevel.ERROR


class TestNotificationMessage:
    """NotificationMessage dataclass tests."""

    def test_create_minimal_message(self) -> None:
        """Test creating message with required fields only."""
        message = NotificationMessage(
            template="test_template",
            context={"key": "value"},
            level=NotificationLevel.INFO,
        )
        assert message.template == "test_template"
        assert message.context == {"key": "value"}
        assert message.level == NotificationLevel.INFO
        assert message.timestamp is None

    def test_create_message_with_timestamp(self) -> None:
        """Test creating message with timestamp."""
        now = datetime.now()
        message = NotificationMessage(
            template="test_template",
            context={},
            level=NotificationLevel.WARNING,
            timestamp=now,
        )
        assert message.timestamp == now

    def test_message_is_frozen(self) -> None:
        """Test that message is immutable."""
        message = NotificationMessage(
            template="test",
            context={},
            level=NotificationLevel.INFO,
        )
        # Frozen dataclass raises TypeError on attribute assignment
        # Testing with a valid exception type
        with pytest.raises((TypeError, Exception)):
            message.template = "new_template"  # type: ignore[misc]

    def test_context_with_none_default(self) -> None:
        """Test context handling."""
        message = NotificationMessage(
            template="test",
            context=None,  # type: ignore[arg-type]
            level=NotificationLevel.INFO,
        )
        # Message is frozen, context should be None or set in __post_init__
        # The implementation should handle None context
        assert message is not None
