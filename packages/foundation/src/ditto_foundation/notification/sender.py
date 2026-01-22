"""Notification channel senders."""

from abc import ABC, abstractmethod


class NotificationSender(ABC):
    """Abstract base class for notification senders."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """
        Get channel identifier.

        Returns:
            Channel name (e.g., "email", "telegram", "webhook").

        """
        ...

    @abstractmethod
    def send(self, rendered_content: str) -> bool:
        """
        Send rendered notification content.

        Args:
            rendered_content: Already rendered content for this channel.

        Returns:
            True if send was successful, False otherwise.

        """
        ...


__all__ = ["NotificationSender"]
