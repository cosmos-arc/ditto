"""Tests for alert base classes."""

import pytest
from ditto_datahub.alerts.base import AlertLevel, AlertMessage, AlertSender


class TestAlertLevel:
    """Tests for AlertLevel enum."""

    def test_alert_level_values(self) -> None:
        """Test AlertLevel has correct values."""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"

    def test_alert_level_ordering(self) -> None:
        """Test AlertLevel severity ordering."""
        # CRITICAL > ERROR > WARNING > INFO
        assert AlertLevel.CRITICAL > AlertLevel.ERROR
        assert AlertLevel.ERROR > AlertLevel.WARNING
        assert AlertLevel.WARNING > AlertLevel.INFO


class TestAlertMessage:
    """Tests for AlertMessage dataclass."""

    def test_create_alert_message(self) -> None:
        """Test creating an AlertMessage."""
        message = AlertMessage(
            level=AlertLevel.ERROR,
            title="Test Alert",
            content="Test content",
            context={"key": "value"},
        )

        assert message.level == AlertLevel.ERROR
        assert message.title == "Test Alert"
        assert message.content == "Test content"
        assert message.context == {"key": "value"}

    def test_alert_message_without_context(self) -> None:
        """Test AlertMessage without optional context."""
        message = AlertMessage(
            level=AlertLevel.INFO,
            title="Info",
            content="Info content",
        )

        assert message.level == AlertLevel.INFO
        assert message.context == {}

    def test_alert_message_format(self) -> None:
        """Test AlertMessage format method."""
        message = AlertMessage(
            level=AlertLevel.WARNING,
            title="Warning Alert",
            content="This is a warning",
        )

        formatted = message.format()
        assert "[WARNING]" in formatted
        assert "Warning Alert" in formatted
        assert "This is a warning" in formatted


class TestAlertSenderABC:
    """Tests for AlertSender abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test AlertSender cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AlertSender()  # type: ignore[abstract]

    def test_subclass_must_implement_send(self) -> None:
        """Test subclass must implement send method."""

        class IncompleteSender(AlertSender):
            pass

        with pytest.raises(TypeError):
            IncompleteSender()

    def test_complete_subclass_can_be_instantiated(self) -> None:
        """Test complete subclass can be instantiated."""

        class CompleteSender(AlertSender):
            @property
            def name(self) -> str:
                return "complete"

            def send(self, message: AlertMessage) -> bool:
                return True

        # Should not raise
        sender = CompleteSender()
        assert isinstance(sender, AlertSender)

    def test_sender_with_name_property(self) -> None:
        """Test AlertSender has name property."""

        class DummySender(AlertSender):
            @property
            def name(self) -> str:
                return "dummy"

            def send(self, message: AlertMessage) -> bool:
                return True

        sender = DummySender()
        assert sender.name == "dummy"
