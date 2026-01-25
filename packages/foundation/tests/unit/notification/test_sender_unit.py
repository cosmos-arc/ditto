"""Notification sender unit tests."""

import pytest
from ditto_foundation.notification.sender import NotificationSender


class MockNotificationSender(NotificationSender):
    """Mock implementation for testing."""

    def __init__(self, channel_name: str = "mock") -> None:
        self._channel_name = channel_name
        self.last_sent_content: str | None = None
        self.send_result: bool = True

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, rendered_content: str) -> bool:
        self.last_sent_content = rendered_content
        return self.send_result


class TestNotificationSender:
    """NotificationSender abstract base class tests."""

    def test_cannot_instantiate_abstract(self) -> None:
        """Test that NotificationSender cannot be instantiated directly."""
        with pytest.raises(TypeError):
            NotificationSender()  # type: ignore[abstract]

    def test_mock_implementation(self) -> None:
        """Test that mock implementation works correctly."""
        sender = MockNotificationSender()
        assert sender.channel_name == "mock"
        assert sender.send("test content") is True
        assert sender.last_sent_content == "test content"

    def test_custom_channel_name(self) -> None:
        """Test custom channel name."""
        sender = MockNotificationSender(channel_name="custom")
        assert sender.channel_name == "custom"

    def test_send_failure(self) -> None:
        """Test send failure scenario."""
        sender = MockNotificationSender()
        sender.send_result = False
        assert sender.send("test") is False

    def test_send_stores_content(self) -> None:
        """Test that send method stores the content."""
        sender = MockNotificationSender()
        sender.send("content 1")
        assert sender.last_sent_content == "content 1"
        sender.send("content 2")
        assert sender.last_sent_content == "content 2"
