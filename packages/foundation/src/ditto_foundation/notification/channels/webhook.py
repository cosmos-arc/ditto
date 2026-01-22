"""Webhook notification channel (generic HTTP webhook)."""

from typing import TYPE_CHECKING

from loguru import logger

from ditto_foundation.notification.config import NotificationSettings
from ditto_foundation.notification.sender import NotificationSender

if TYPE_CHECKING:
    import httpx
else:
    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]


class WebhookSender(NotificationSender):
    """
    Generic webhook notification sender via HTTP POST.

    Supports Telegram, WeChat, DingTalk, Slack, and custom webhooks.
    """

    def __init__(self, settings: NotificationSettings) -> None:
        """
        Initialize webhook sender with settings.

        Args:
            settings: Notification settings with webhook configuration.

        Raises:
            ImportError: If httpx is not available.

        """
        if httpx is None:
            raise ImportError("httpx is required for WebhookSender")

        self._settings = settings

    @property
    def channel_name(self) -> str:
        """Get channel identifier."""
        return "webhook"

    def send(self, rendered_content: str) -> bool:
        """
        Send rendered content via HTTP POST webhook.

        Args:
            rendered_content: Rendered content (plain text or JSON) to send.

        Returns:
            True if send was successful, False otherwise.

        """
        if not self._settings.webhook_url:
            logger.warning(
                "Webhook URL not configured",
                event="webhook_not_configured",
            )
            return False

        try:
            headers = {"Content-Type": "text/plain; charset=utf-8"}
            headers.update(self._settings.webhook_headers)

            # Type narrowing: httpx is guaranteed to be available after __init__
            assert httpx is not None  # noqa: S101
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    self._settings.webhook_url,
                    content=rendered_content.encode("utf-8"),
                    headers=headers,
                )
                response.raise_for_status()

            logger.info(
                "Webhook sent successfully",
                event="webhook_sent",
                url=self._settings.webhook_url,
            )
            return True

        except Exception as e:
            logger.error(
                "Webhook send failed",
                event="webhook_error",
                error=str(e),
            )
            return False


__all__ = ["WebhookSender"]
