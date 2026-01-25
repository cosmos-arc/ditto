"""Notification channel senders."""

from ditto_foundation.notification.channels.email import EmailSender
from ditto_foundation.notification.channels.telegram import TelegramSender
from ditto_foundation.notification.channels.webhook import WebhookSender

__all__ = [
    "EmailSender",
    "TelegramSender",
    "WebhookSender",
]
