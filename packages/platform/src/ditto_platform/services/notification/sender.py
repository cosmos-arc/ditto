"""通知渠道发送器."""

from typing import Protocol


class NotificationSender(Protocol):
    """Protocol for notification senders."""

    @property
    def channel_name(self) -> str:
        """
        Get channel identifier.

        Returns:
            Channel name (e.g., "email", "telegram", "webhook").

        """
        ...

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
