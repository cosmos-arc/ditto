"""
Notification 组件注册 (DI Provider).

提供 AlertManager 及其依赖的 TemplateEngine 和 NotificationSender 实例。
"""

from __future__ import annotations

import smtplib
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

from dishka import Provider, Scope, provide
from ditto_infra.services.notification import NotificationSettings
from ditto_infra.services.notification.channels import EmailSender, WebhookSender
from ditto_infra.services.notification.manager import AlertManager
from ditto_infra.services.notification.sender import NotificationSender
from ditto_infra.services.notification.template import TemplateEngine
from loguru import logger

__all__ = ["NotificationProvider"]


def _mask_webhook_url(url: str) -> str:
    """安全地记录 webhook URL，只保留 host 部分。"""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/***"
    except Exception:
        return "***"


class NotificationProvider(Provider):
    """
    Notification 组件 Provider.

    职责：
        1. 提供 TemplateEngine
        2. 提供配置的 NotificationSender 列表
        3. 提供 AlertManager（组合以上组件）

    模板路径：
        ditto_infra.services.notification.templates（合并后的统一模板）

    """

    scope = Scope.APP

    @provide
    def template_engine(self) -> TemplateEngine:
        """
        模板引擎（应用级单例）.

        Returns:
            TemplateEngine: 配置好的模板引擎实例

        """
        # 模板路径（已合并到 infra）
        templates = files("ditto_infra.services.notification.templates")
        template_path = Path(str(templates))

        logger.debug(
            "Template engine initialized",
            path=str(template_path),
        )

        return TemplateEngine([template_path])

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
            except (smtplib.SMTPException, ConnectionError, TimeoutError) as e:
                logger.warning(
                    "email_sender_initialization_failed",
                    error_type=type(e).__name__,
                )

        # Webhook 发送器（通用）
        if notification_settings.webhook_url:
            try:
                senders.append(WebhookSender(notification_settings))
                logger.info(
                    "Webhook sender initialized",
                    url=_mask_webhook_url(notification_settings.webhook_url),
                )
            except (ConnectionError, TimeoutError, ValueError) as e:
                logger.warning(
                    "webhook_sender_initialization_failed",
                    error_type=type(e).__name__,
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
