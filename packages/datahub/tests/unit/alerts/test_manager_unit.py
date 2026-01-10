"""Tests for AlertManager."""

from ditto_datahub.alerts.base import AlertLevel, AlertMessage
from ditto_datahub.alerts.manager import (
    AlertManager,
    LoggingAlertSender,
    create_default_manager,
)


class MockAlertSender:
    """Mock alert sender for testing."""

    def __init__(self, name: str, should_fail: bool = False) -> None:
        self.name = name
        self.should_fail = should_fail
        self.sent_messages: list[AlertMessage] = []

    def send(self, message: AlertMessage) -> bool:
        if self.should_fail:
            return False
        self.sent_messages.append(message)
        return True


class TestAlertManager:
    """Tests for AlertManager."""

    def test_send_alert_with_single_sender(self) -> None:
        """Test sending alert with single sender."""
        sender = MockAlertSender("test")
        manager = AlertManager([sender])

        results = manager.send_alert(
            level=AlertLevel.INFO,
            title="Test",
            message="Test message",
        )

        assert results == {"test": True}
        assert len(sender.sent_messages) == 1
        assert sender.sent_messages[0].title == "Test"

    def test_send_alert_with_multiple_senders(self) -> None:
        """Test sending alert with multiple senders."""
        sender1 = MockAlertSender("sender1")
        sender2 = MockAlertSender("sender2")
        manager = AlertManager([sender1, sender2])

        results = manager.send_alert(
            level=AlertLevel.WARNING,
            title="Warning",
            message="Warning message",
        )

        assert results == {"sender1": True, "sender2": True}
        assert len(sender1.sent_messages) == 1
        assert len(sender2.sent_messages) == 1

    def test_send_alert_with_failed_sender(self) -> None:
        """Test sending alert when one sender fails."""
        sender1 = MockAlertSender("sender1")
        sender2 = MockAlertSender("sender2", should_fail=True)
        manager = AlertManager([sender1, sender2])

        results = manager.send_alert(
            level=AlertLevel.ERROR,
            title="Error",
            message="Error message",
        )

        assert results == {"sender1": True, "sender2": False}
        assert len(sender1.sent_messages) == 1
        assert len(sender2.sent_messages) == 0

    def test_alert_ingestion_failure(self) -> None:
        """Test ingestion failure alert."""
        sender = MockAlertSender("test")
        manager = AlertManager([sender])

        manager.alert_ingestion_failure(
            dataset="etf_daily",
            trade_date="2024-12-27",
            error="Connection timeout",
        )

        assert len(sender.sent_messages) == 1
        msg = sender.sent_messages[0]
        assert msg.level == AlertLevel.ERROR
        assert "数据摄取失败" in msg.title
        assert "etf_daily" in msg.title
        assert msg.context["dataset"] == "etf_daily"
        assert msg.context["trade_date"] == "2024-12-27"
        assert msg.context["error"] == "Connection timeout"

    def test_alert_dq_failure_with_errors(self) -> None:
        """Test DQ failure alert with errors."""
        sender = MockAlertSender("test")
        manager = AlertManager([sender])

        manager.alert_dq_failure(
            dataset="stock_daily",
            trade_date="2024-12-27",
            failed_rules=["null_check", "price_range"],
            error_count=5,
        )

        assert len(sender.sent_messages) == 1
        msg = sender.sent_messages[0]
        assert msg.level == AlertLevel.ERROR
        assert "数据质量检查失败" in msg.title
        assert msg.context["error_count"] == 5

    def test_alert_dq_failure_with_warnings_only(self) -> None:
        """Test DQ failure alert with warnings only."""
        sender = MockAlertSender("test")
        manager = AlertManager([sender])

        manager.alert_dq_failure(
            dataset="stock_daily",
            trade_date="2024-12-27",
            failed_rules=["price_range"],
            error_count=0,
        )

        assert len(sender.sent_messages) == 1
        msg = sender.sent_messages[0]
        assert msg.level == AlertLevel.WARNING
        assert msg.context["error_count"] == 0


class TestLoggingAlertSender:
    """Tests for LoggingAlertSender."""

    def test_logging_sender_returns_true(self) -> None:
        """Test LoggingAlertSender always returns True."""
        sender = LoggingAlertSender()
        message = AlertMessage(
            level=AlertLevel.INFO,
            title="Test",
            content="Test content",
        )

        result = sender.send(message)

        assert result is True

    def test_logging_sender_name(self) -> None:
        """Test LoggingAlertSender name property."""
        sender = LoggingAlertSender()
        assert sender.name == "logging"


class TestCreateDefaultManager:
    """Tests for create_default_manager factory."""

    def test_create_default_manager_returns_manager(self) -> None:
        """Test create_default_manager returns AlertManager."""
        manager = create_default_manager()

        assert isinstance(manager, AlertManager)

    def test_default_manager_has_logging_sender(self) -> None:
        """Test default manager includes LoggingAlertSender."""
        manager = create_default_manager()

        results = manager.send_alert(
            level=AlertLevel.INFO,
            title="Test",
            message="Test",
        )

        assert results == {"logging": True}
