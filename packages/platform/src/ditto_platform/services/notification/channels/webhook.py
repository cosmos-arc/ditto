"""Webhook notification channel (generic HTTP webhook)."""

import httpx
from loguru import logger

from ditto_platform.services.notification.config import NotificationSettings


class WebhookSender:
    """
    Generic webhook notification sender via HTTP POST.

    Supports custom webhooks for:
    - WeChat (企业微信)
    - DingTalk (钉钉)
    - Slack
    - Custom endpoints

    Note: For Telegram, use TelegramSender for direct Bot API integration,
    or use WebhookSender with a Telegram webhook URL if you have a proxy service.
    """

    def __init__(self, settings: NotificationSettings) -> None:
        """
        Initialize webhook sender with settings.

        Args:
            settings: Notification settings with webhook configuration.

        """
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

            with httpx.Client(timeout=30) as client:
                response = client.post(
                    self._settings.webhook_url,
                    content=rendered_content.encode("utf-8"),
                    headers=headers,
                )
                response.raise_for_status()

            logger.info("Webhook sent successfully", event="webhook_sent")
            return True

        except httpx.TimeoutException as e:
            logger.warning(
                "Webhook timeout",
                event="webhook_timeout",
                error=str(e),
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.error(
                "Webhook HTTP error",
                event="webhook_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            return False
        except httpx.NetworkError as e:
            logger.error(
                "Webhook network error",
                event="webhook_network_error",
                error=str(e),
            )
            return False
        except Exception as e:
            # 未预期的错误应该抛出，让调用方处理
            logger.error(
                "Webhook send failed with unexpected error",
                event="webhook_unexpected_error",
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            raise


__all__ = ["WebhookSender"]
