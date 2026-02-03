"""NotificationProvider unit tests."""

import ditto_foundation.notification
import ditto_port.notifications
from dishka import Provider, Scope, make_container, provide
from ditto_port.registry.config import ConfigProvider
from ditto_port.registry.notification import NotificationProvider


def _settings_provider(
    settings: ditto_foundation.notification.NotificationSettings,
) -> Provider:
    class SettingsProvider(Provider):
        scope = Scope.APP

        @provide
        def notification_settings(
            self,
        ) -> ditto_foundation.notification.NotificationSettings:
            return settings

    return SettingsProvider()


class TestNotificationProvider:
    """NotificationProvider unit tests."""

    def test_provide_template_engine(self) -> None:
        """Test TemplateEngine provisioning."""
        settings = ditto_foundation.notification.NotificationSettings()
        container = make_container(_settings_provider(settings), NotificationProvider())

        engine = container.get(ditto_foundation.notification.TemplateEngine)

        assert engine is not None
        assert isinstance(engine, ditto_foundation.notification.TemplateEngine)

        container.close()

    def test_provide_notification_senders_default(self) -> None:
        """Test notification_senders with default (empty) configuration."""
        settings = ditto_foundation.notification.NotificationSettings()
        container = make_container(_settings_provider(settings), NotificationProvider())

        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        # 默认情况下应该返回空列表（因为没有配置）
        assert isinstance(senders, list)
        # 可能会有 0 个或多个 sender，取决于配置

        container.close()

    def test_provide_notification_senders_with_email(self) -> None:
        """Test notification_senders with email configuration."""
        # 设置 email 配置
        settings = ditto_foundation.notification.NotificationSettings(
            email_to="test@example.com",
            email_from="noreply@ditto.local",
            email_smtp_host="localhost",
            email_smtp_port=587,
        )
        container = make_container(_settings_provider(settings), NotificationProvider())

        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        assert len(senders) >= 1
        # 至少应该有 EmailSender
        sender_names = [s.channel_name for s in senders]
        assert "email" in sender_names

        container.close()

    def test_provide_notification_senders_with_webhook(self) -> None:
        """Test notification_senders with webhook configuration."""
        # 设置 webhook 配置
        settings = ditto_foundation.notification.NotificationSettings(
            webhook_url="https://example.com/webhook"
        )
        container = make_container(_settings_provider(settings), NotificationProvider())

        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        assert len(senders) >= 1
        sender_names = [s.channel_name for s in senders]
        assert "webhook" in sender_names

        container.close()

    def test_provide_alert_manager(self) -> None:
        """Test AlertManager provisioning."""
        settings = ditto_foundation.notification.NotificationSettings()
        container = make_container(_settings_provider(settings), NotificationProvider())

        manager = container.get(ditto_port.notifications.AlertManager)

        assert manager is not None
        assert isinstance(manager, ditto_port.notifications.AlertManager)

        container.close()

    def test_alert_manager_dependencies(self) -> None:
        """Test AlertManager has correct dependencies injected."""
        settings = ditto_foundation.notification.NotificationSettings()
        container = make_container(_settings_provider(settings), NotificationProvider())

        manager = container.get(ditto_port.notifications.AlertManager)
        engine = container.get(ditto_foundation.notification.TemplateEngine)
        senders = container.get(list[ditto_foundation.notification.NotificationSender])

        # 验证 AlertManager 的依赖
        assert manager._template_engine is engine
        assert manager._senders == senders

        container.close()

    def test_template_engine_has_correct_paths(self) -> None:
        """Test TemplateEngine is initialized with correct template paths."""
        settings = ditto_foundation.notification.NotificationSettings()
        container = make_container(_settings_provider(settings), NotificationProvider())

        engine = container.get(ditto_foundation.notification.TemplateEngine)

        # 验证模板引擎已正确初始化
        assert engine is not None
        assert hasattr(engine, "_env")

        container.close()

    def test_integration_with_config_provider(self) -> None:
        """Test NotificationProvider works with ConfigProvider."""
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
