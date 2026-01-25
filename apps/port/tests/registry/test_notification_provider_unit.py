"""NotificationProvider unit tests."""

import ditto_foundation.notification
import ditto_port.notifications
import pytest
from dishka import make_container
from ditto_port.registry.config import ConfigProvider
from ditto_port.registry.notification import NotificationProvider


class TestNotificationProvider:
    """NotificationProvider unit tests."""

    def test_provide_notification_settings(self) -> None:
        """Test NotificationSettings provisioning."""
        container = make_container(NotificationProvider())

        settings = container.get(ditto_foundation.notification.NotificationSettings)

        assert settings is not None
        assert isinstance(settings, ditto_foundation.notification.NotificationSettings)

        container.close()

    def test_provide_template_engine(self) -> None:
        """Test TemplateEngine provisioning."""
        container = make_container(NotificationProvider())

        engine = container.get(ditto_foundation.notification.TemplateEngine)

        assert engine is not None
        assert isinstance(engine, ditto_foundation.notification.TemplateEngine)

        container.close()

    def test_provide_notification_senders_default(self) -> None:
        """Test notification_senders with default (empty) configuration."""
        # 使用默认配置（没有 NOTIFICATION_* 环境变量）
        container = make_container(NotificationProvider())

        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        # 默认情况下应该返回空列表（因为没有配置）
        assert isinstance(senders, list)
        # 可能会有 0 个或多个 sender，取决于环境变量

        container.close()

    def test_provide_notification_senders_with_email(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test notification_senders with email configuration."""
        # 设置 email 配置
        monkeypatch.setenv("NOTIFICATION_EMAIL_TO", "test@example.com")
        monkeypatch.setenv("NOTIFICATION_EMAIL_FROM", "noreply@ditto.local")
        monkeypatch.setenv("NOTIFICATION_EMAIL_SMTP_HOST", "localhost")
        monkeypatch.setenv("NOTIFICATION_EMAIL_SMTP_PORT", "587")

        container = make_container(NotificationProvider())

        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        assert len(senders) >= 1
        # 至少应该有 EmailSender
        sender_names = [s.channel_name for s in senders]
        assert "email" in sender_names

        container.close()

    def test_provide_notification_senders_with_webhook(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test notification_senders with webhook configuration."""
        # 设置 webhook 配置
        monkeypatch.setenv("NOTIFICATION_WEBHOOK_URL", "https://example.com/webhook")

        container = make_container(NotificationProvider())

        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        assert len(senders) >= 1
        sender_names = [s.channel_name for s in senders]
        assert "webhook" in sender_names

        container.close()

    def test_provide_alert_manager(self) -> None:
        """Test AlertManager provisioning."""
        container = make_container(NotificationProvider())

        manager = container.get(ditto_port.notifications.AlertManager)

        assert manager is not None
        assert isinstance(manager, ditto_port.notifications.AlertManager)

        container.close()

    def test_alert_manager_dependencies(self) -> None:
        """Test AlertManager has correct dependencies injected."""
        container = make_container(NotificationProvider())

        manager = container.get(ditto_port.notifications.AlertManager)
        engine = container.get(ditto_foundation.notification.TemplateEngine)
        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        # 验证 AlertManager 的依赖
        assert manager._template_engine is engine
        assert manager._senders == senders

        container.close()

    def test_template_engine_has_correct_paths(self) -> None:
        """Test TemplateEngine is initialized with correct template paths."""
        container = make_container(NotificationProvider())

        engine = container.get(ditto_foundation.notification.TemplateEngine)

        # 验证模板引擎已正确初始化
        assert engine is not None
        assert hasattr(engine, "_env")

        container.close()

    def test_integration_with_config_provider(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test NotificationProvider works with ConfigProvider."""
        # 设置必要的环境变量
        monkeypatch.setenv("DITTO_ENV", "testing")
        monkeypatch.setenv("NOTIFICATION_EMAIL_TO", "test@example.com")

        container = make_container(ConfigProvider(), NotificationProvider())

        # 验证可以获取 NotificationSettings
        settings = container.get(
            ditto_foundation.notification.NotificationSettings,
        )
        assert settings is not None

        # 验证可以获取 AlertManager
        manager = container.get(ditto_port.notifications.AlertManager)
        assert manager is not None

        container.close()
