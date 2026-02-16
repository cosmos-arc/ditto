"""业务级通知管理器."""

from datetime import datetime
from typing import Any

from loguru import logger

from ditto_infra.services.notification.message import (
    Notification,
    NotificationLevel,
)
from ditto_infra.services.notification.sender import NotificationSender
from ditto_infra.services.notification.template import TemplateEngine


class AlertManager:
    """
    Business-level alert management.

    Coordinates template rendering and multi-channel notification delivery.
    Uses Foundation's TemplateEngine and NotificationSender for actual
    rendering and delivery.

    Args:
        template_engine: Template engine for rendering notifications
        senders: List of notification senders for different channels

    """

    def __init__(
        self,
        template_engine: TemplateEngine,
        senders: list[NotificationSender],
    ) -> None:
        """
        Initialize AlertManager.

        Args:
            template_engine: Template engine instance
            senders: List of notification senders

        """
        self._template_engine = template_engine
        self._senders = senders

    def send_alert(
        self,
        template: str,
        context: dict[str, Any],
        level: NotificationLevel,
        timestamp: datetime | None = None,
    ) -> dict[str, bool]:
        """
        Send alert to all configured channels.

        Args:
            template: Template name (e.g., "dq_failure")
            context: Template variables for rendering
            level: Notification severity level
            timestamp: Optional timestamp for the notification

        Returns:
            Dictionary mapping channel names to send success status

        """
        # Create notification message
        message = Notification(
            template=template,
            context=context,
            level=level,
            timestamp=timestamp,
        )

        results: dict[str, bool] = {}

        # Send to each channel
        for sender in self._senders:
            try:
                # Render message for this channel
                rendered = self._template_engine.render(message, sender.channel_name)

                # Send rendered content
                success = sender.send(rendered)
                results[sender.channel_name] = success

                if success:
                    logger.info(
                        "Alert sent successfully",
                        channel=sender.channel_name,
                        template=template,
                        level=level.value,
                    )
                else:
                    logger.warning(
                        "Alert send failed",
                        channel=sender.channel_name,
                        template=template,
                        level=level.value,
                    )

            except Exception as e:
                # Catch exceptions to prevent one channel failure from affecting others
                logger.error(
                    "Error sending alert",
                    channel=sender.channel_name,
                    template=template,
                    error=str(e),
                )
                results[sender.channel_name] = False

        return results
