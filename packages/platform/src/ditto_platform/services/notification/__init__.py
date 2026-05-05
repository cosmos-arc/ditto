"""
通知服务基础设施.

包含:
- 发送能力: NotificationSender, EmailSender, WebhookSender, TelegramSender
- 消息模型: Notification, NotificationLevel
- 模板引擎: TemplateEngine
- 告警编排: AlertManager
"""

from ditto_platform.services.notification.channels.email import EmailSender
from ditto_platform.services.notification.channels.telegram import TelegramSender
from ditto_platform.services.notification.channels.webhook import WebhookSender
from ditto_platform.services.notification.config import NotificationSettings
from ditto_platform.services.notification.manager import AlertManager
from ditto_platform.services.notification.message import (
    Notification,
    NotificationLevel,
)
from ditto_platform.services.notification.sender import NotificationSender
from ditto_platform.services.notification.template import TemplateEngine

__all__ = [
    "AlertManager",
    "EmailSender",
    "Notification",
    "NotificationLevel",
    "NotificationSender",
    "NotificationSettings",
    "TelegramSender",
    "TemplateEngine",
    "WebhookSender",
]
