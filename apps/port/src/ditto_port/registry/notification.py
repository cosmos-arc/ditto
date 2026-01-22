"""
Notification 组件注册 (DI Provider).

提供 AlertManager 及其依赖的 TemplateEngine 和 NotificationSender 实例。
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_foundation.notification import NotificationSettings
from ditto_foundation.notification.channels import EmailSender, WebhookSender
from ditto_foundation.notification.sender import NotificationSender
from ditto_foundation.notification.template import TemplateEngine
from loguru import logger

from ditto_port.notifications.manager import AlertManager

__all__ = ["NotificationProvider"]


class NotificationProvider(Provider):
    """
    Notification 组件 Provider.

    职责：
        1. 提供 NotificationSettings 配置
        2. 提供 TemplateEngine（支持模板 fallback）
        3. 提供配置的 NotificationSender 列表
        4. 提供 AlertManager（组合以上组件）

    模板路径优先级：
        1. Port 应用模板（ditto_port/notifications/templates）
        2. Foundation 基础模板（ditto_foundation/notification/templates）

    """

    scope = Scope.APP

    @provide
    def notification_settings(self) -> NotificationSettings:
        """
        Notification 配置（应用级单例）.

        从环境变量加载，前缀为 NOTIFICATION_。
        """
        try:
            return NotificationSettings()
        except Exception as e:
            logger.warning(
                "Failed to load notification settings, using defaults",
                error=str(e),
            )
            return NotificationSettings()

    @provide
    def template_engine(self) -> TemplateEngine:
        """
        模板引擎（应用级单例）.

        支持模板 fallback：Port 应用模板优先，Foundation 模板作为后备。

        Returns:
            TemplateEngine: 配置好的模板引擎实例

        """
        # Port 应用模板路径（优先）
        port_templates = files("ditto_port.notifications.templates")
        port_template_path = Path(str(port_templates))

        # Foundation 基础模板路径（后备）
        foundation_templates = files("ditto_foundation.notification.templates")
        foundation_template_path = Path(str(foundation_templates))

        # 构建 template paths 列表（优先级从高到低）
        template_paths = [port_template_path, foundation_template_path]

        logger.debug(
            "Template engine initialized",
            paths=[str(p) for p in template_paths],
        )

        return TemplateEngine(template_paths)

    @provide
    def notification_senders(
        self,
        notification_settings: NotificationSettings,
    ) -> list[NotificationSender]:
        """
        Notification 发送器列表（应用级单例）.

        根据配置动态创建可用的发送器。

        Args:
            notification_settings: Notification 配置

        Returns:
            list[NotificationSender]: 可用的发送器列表

        """
        senders: list[NotificationSender] = []

        # Email 发送器
        if notification_settings.email_to:
            try:
                senders.append(EmailSender(notification_settings))
                logger.info(
                    "Email sender initialized",
                    recipients=notification_settings.email_to,
                )
            except Exception as e:
                logger.warning(
                    "Failed to initialize email sender",
                    error=str(e),
                )

        # Webhook 发送器（通用）
        if notification_settings.webhook_url:
            try:
                senders.append(WebhookSender(notification_settings))
                logger.info(
                    "Webhook sender initialized",
                    url=notification_settings.webhook_url,
                )
            except Exception as e:
                logger.warning(
                    "Failed to initialize webhook sender",
                    error=str(e),
                )

        # 可以在此添加更多发送器（Telegram, WeChat, DingTalk, Slack）

        logger.info(
            "Notification senders initialized",
            count=len(senders),
            channels=[s.channel_name for s in senders],
        )

        return senders

    @provide
    def alert_manager(
        self,
        template_engine: TemplateEngine,
        notification_senders: list[NotificationSender],
    ) -> AlertManager:
        """
        Alert 管理器（应用级单例）.

        组合 TemplateEngine 和 NotificationSenders 提供业务级通知能力。

        Args:
            template_engine: 模板引擎
            notification_senders: 发送器列表

        Returns:
            AlertManager: Alert 管理器实例

        """
        return AlertManager(
            template_engine=template_engine,
            senders=notification_senders,
        )
