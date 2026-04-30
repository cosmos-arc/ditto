"""
通知服务 - 可含业务上下文的基础服务.

包含:
- 通用发送能力: NotificationSender, EmailSender, WebhookSender, TelegramSender
- 消息模型: Notification, NotificationLevel
- 模板引擎: TemplateEngine
- 业务告警: AlertManager, alert_dq_failure, alert_ingestion_failure
"""

from ditto_platform.services.notification.business import (
    alert_dq_failure,
    alert_ingestion_failure,
)
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
    "alert_dq_failure",
    "alert_ingestion_failure",
]
