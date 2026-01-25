"""Notification message types."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class NotificationLevel(str, Enum):
    """Notification severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def __lt__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, NotificationLevel):
            return NotImplemented
        order = [
            NotificationLevel.INFO,
            NotificationLevel.WARNING,
            NotificationLevel.ERROR,
            NotificationLevel.CRITICAL,
        ]
        return order.index(self) < order.index(other)

    def __le__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, NotificationLevel):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, NotificationLevel):
            return NotImplemented
        return not self <= other

    def __ge__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, NotificationLevel):
            return NotImplemented
        return self == other or self > other


@dataclass(frozen=True)
class Notification:
    """
    Structure notification message (format-agnostic).

    The actual content is rendered by template engine in each channel.

    Args:
        template: Template name (e.g., "dq_failure")
        context: Template variables for rendering
        level: Notification severity level
        timestamp: Optional timestamp for the notification

    """

    template: str
    context: dict[str, Any]
    level: NotificationLevel
    timestamp: datetime | None = None


__all__ = [
    "Notification",
    "NotificationLevel",
]
