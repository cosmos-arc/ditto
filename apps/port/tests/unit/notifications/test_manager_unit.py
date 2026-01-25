"""AlertManager unit tests."""

from datetime import datetime
from pathlib import Path

from ditto_foundation.notification.message import (
    NotificationLevel,
)
from ditto_foundation.notification.sender import NotificationSender
from ditto_foundation.notification.template import TemplateEngine


class MockNotificationSender(NotificationSender):
    """Mock implementation for testing."""

    def __init__(self, channel_name: str = "mock", send_result: bool = True) -> None:
        self._channel_name = channel_name
        self.send_result = send_result
        self.last_sent_content: str | None = None
        self.send_count = 0

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, rendered_content: str) -> bool:
        self.last_sent_content = rendered_content
        self.send_count += 1
        return self.send_result


class TestAlertManager:
    """AlertManager unit tests."""

    def test_init_with_dependencies(self, tmp_path: Path) -> None:
        """Test initialization with TemplateEngine and senders."""
        from ditto_port.notifications.manager import AlertManager

        # Create template engine with temp path
        template_engine = TemplateEngine([tmp_path])

        # Create mock senders
        sender1 = MockNotificationSender(channel_name="telegram")
        sender2 = MockNotificationSender(channel_name="email")

        # Initialize manager
        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender1, sender2],
        )

        assert manager is not None
        assert manager._template_engine is template_engine
        assert len(manager._senders) == 2

    def test_send_alert_success(
        self,
        tmp_path: Path,
    ) -> None:
        """Test successful alert sending."""
        from ditto_port.notifications.manager import AlertManager

        # Create test template
        template_file = tmp_path / "test_alert_telegram.j2"
        template_file.write_text("Alert: {{ message }} (Level: {{ level }})")

        template_engine = TemplateEngine([tmp_path])
        sender = MockNotificationSender(channel_name="telegram")

        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender],
        )

        # Send alert
        result = manager.send_alert(
            template="test_alert",
            context={"message": "Test error occurred"},
            level=NotificationLevel.ERROR,
        )

        assert result == {"telegram": True}
        assert sender.send_count == 1
        assert "Alert: Test error occurred" in sender.last_sent_content
        assert "Level: error" in sender.last_sent_content

    def test_send_alert_multiple_senders(self, tmp_path: Path) -> None:
        """Test alert sending to multiple channels."""
        from ditto_port.notifications.manager import AlertManager

        # Create templates for each channel
        (tmp_path / "multi_telegram.j2").write_text("Telegram: {{ msg }}")
        (tmp_path / "multi_email.j2").write_text("Email: {{ msg }}")

        template_engine = TemplateEngine([tmp_path])
        sender1 = MockNotificationSender(channel_name="telegram")
        sender2 = MockNotificationSender(channel_name="email")

        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender1, sender2],
        )

        result = manager.send_alert(
            template="multi",
            context={"msg": "Test message"},
            level=NotificationLevel.INFO,
        )

        assert result == {"telegram": True, "email": True}
        assert sender1.send_count == 1
        assert sender2.send_count == 1
        assert sender1.last_sent_content == "Telegram: Test message"
        assert sender2.last_sent_content == "Email: Test message"

    def test_send_alert_partial_failure(self, tmp_path: Path) -> None:
        """Test alert sending when one sender fails."""
        from ditto_port.notifications.manager import AlertManager

        # Create templates for both channels
        (tmp_path / "partial_telegram.j2").write_text("Telegram: {{ msg }}")
        (tmp_path / "partial_webhook.j2").write_text("Webhook: {{ msg }}")

        template_engine = TemplateEngine([tmp_path])
        sender1 = MockNotificationSender(channel_name="telegram", send_result=True)
        sender2 = MockNotificationSender(channel_name="webhook", send_result=False)

        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender1, sender2],
        )

        result = manager.send_alert(
            template="partial",
            context={"msg": "Test"},
            level=NotificationLevel.WARNING,
        )

        # All senders are attempted, results reflect success/failure
        assert result == {"telegram": True, "webhook": False}

    def test_send_alert_with_timestamp(self, tmp_path: Path) -> None:
        """Test alert sending with timestamp."""
        from ditto_port.notifications.manager import AlertManager

        (tmp_path / "ts_telegram.j2").write_text("{{ timestamp }}: {{ msg }}")

        template_engine = TemplateEngine([tmp_path])
        sender = MockNotificationSender(channel_name="telegram")

        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender],
        )

        now = datetime.now()
        result = manager.send_alert(
            template="ts",
            context={"msg": "Test"},
            level=NotificationLevel.CRITICAL,
            timestamp=now,
        )

        assert result == {"telegram": True}
        assert str(now) in sender.last_sent_content

    def test_send_alert_empty_senders(self, tmp_path: Path) -> None:
        """Test alert sending with no senders configured."""
        from ditto_port.notifications.manager import AlertManager

        template_engine = TemplateEngine([tmp_path])

        manager = AlertManager(
            template_engine=template_engine,
            senders=[],
        )

        result = manager.send_alert(
            template="test",
            context={"msg": "Test"},
            level=NotificationLevel.INFO,
        )

        assert result == {}

    def test_template_fallback_to_foundation(self, tmp_path: Path) -> None:
        """Test template fallback to foundation templates."""
        from ditto_port.notifications.manager import AlertManager

        # Primary (port) templates - empty
        port_templates = tmp_path / "port_templates"
        port_templates.mkdir()

        # Secondary (foundation) templates - has the template
        foundation_templates = tmp_path / "foundation_templates"
        foundation_templates.mkdir()
        (foundation_templates / "fallback_telegram.j2").write_text(
            "Foundation template: {{ msg }}"
        )

        # Engine with fallback: port first, then foundation
        template_engine = TemplateEngine([port_templates, foundation_templates])
        sender = MockNotificationSender(channel_name="telegram")

        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender],
        )

        result = manager.send_alert(
            template="fallback",
            context={"msg": "Test"},
            level=NotificationLevel.INFO,
        )

        assert result == {"telegram": True}
        assert "Foundation template: Test" in sender.last_sent_content

    def test_send_alert_different_levels(self, tmp_path: Path) -> None:
        """Test sending alerts with different severity levels."""
        from ditto_port.notifications.manager import AlertManager

        (tmp_path / "level_email.j2").write_text(
            "Severity: {{ level }}, Message: {{ msg }}"
        )

        template_engine = TemplateEngine([tmp_path])
        sender = MockNotificationSender(channel_name="email")

        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender],
        )

        levels = [
            NotificationLevel.INFO,
            NotificationLevel.WARNING,
            NotificationLevel.ERROR,
            NotificationLevel.CRITICAL,
        ]

        for level in levels:
            sender.send_count = 0
            result = manager.send_alert(
                template="level",
                context={"msg": f"Test {level.value}"},
                level=level,
            )

            assert result == {"email": True}
            assert sender.send_count == 1
            assert f"Severity: {level.value}" in sender.last_sent_content

    def test_send_alert_with_complex_context(self, tmp_path: Path) -> None:
        """Test alert sending with complex context data."""
        from ditto_port.notifications.manager import AlertManager

        (tmp_path / "complex_telegram.j2").write_text(
            "Dataset: {{ dataset }}\n"
            "Date: {{ date }}\n"
            "Errors: {{ errors|length }}\n"
            "Details: {% for err in errors %}{{ err }}; {% endfor %}"
        )

        template_engine = TemplateEngine([tmp_path])
        sender = MockNotificationSender(channel_name="telegram")

        manager = AlertManager(
            template_engine=template_engine,
            senders=[sender],
        )

        result = manager.send_alert(
            template="complex",
            context={
                "dataset": "stock_daily",
                "date": "2026-01-22",
                "errors": ["Missing OHLC", "Invalid volume"],
            },
            level=NotificationLevel.ERROR,
        )

        assert result == {"telegram": True}
        content = sender.last_sent_content
        assert "Dataset: stock_daily" in content
        assert "Date: 2026-01-22" in content
        assert "Errors: 2" in content
        assert "Missing OHLC" in content
        assert "Invalid volume" in content
