"""Notification channel senders."""

from ditto_foundation.notification.channels.email import EmailSender
from ditto_foundation.notification.channels.webhook import WebhookSender

__all__ = [
    "EmailSender",
    "WebhookSender",
]
