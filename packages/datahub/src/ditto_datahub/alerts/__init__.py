"""Alert module for sending notifications."""

from ditto_datahub.alerts.base import AlertLevel, AlertMessage, AlertSender
from ditto_datahub.alerts.email import EmailAlertSender
from ditto_datahub.alerts.manager import (
    AlertManager,
    LoggingAlertSender,
    create_default_manager,
)
from ditto_datahub.alerts.telegram import TelegramAlertSender
from ditto_datahub.alerts.wechat import WeChatAlertSender

__all__ = [
    "AlertLevel",
    "AlertManager",
    "AlertMessage",
    "AlertSender",
    "EmailAlertSender",
    "LoggingAlertSender",
    "TelegramAlertSender",
    "WeChatAlertSender",
    "create_default_manager",
]
