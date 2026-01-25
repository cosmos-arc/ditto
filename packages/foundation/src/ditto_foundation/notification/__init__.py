"""
Notification infrastructure.

Provides multi-channel notification capabilities with template-based rendering.
"""

from ditto_foundation.notification.config import NotificationSettings
from ditto_foundation.notification.message import (
    Notification,
    NotificationLevel,
)
from ditto_foundation.notification.sender import NotificationSender
from ditto_foundation.notification.template import TemplateEngine

__all__ = [
    "Notification",
    "NotificationLevel",
    "NotificationSender",
    "NotificationSettings",
    "TemplateEngine",
]
