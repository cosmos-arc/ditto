"""Telegram 通知渠道."""

import httpx
from loguru import logger

from ditto_platform.services.notification.config import NotificationSettings


class TelegramSender:
    """
    Telegram Bot API notification sender.

    Uses Telegram Bot API to send messages directly (not via webhook).
    Requires bot_token and chat_id in NotificationSettings.
    """

    def __init__(self, settings: NotificationSettings) -> None:
        """
        Initialize Telegram sender with settings.

        Args:
            settings: Notification settings with telegram configuration.

        Raises:
            ValueError: If telegram_bot_token or telegram_chat_id is not configured.

        """
        if not settings.telegram_bot_token:
            raise ValueError("telegram_bot_token is required for TelegramSender")
        if not settings.telegram_chat_id:
            raise ValueError("telegram_chat_id is required for TelegramSender")

        self._settings = settings
        self._api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    @property
    def channel_name(self) -> str:
        """Get channel identifier."""
        return "telegram"

    def send(self, rendered_content: str) -> bool:
        """
        Send rendered content via Telegram Bot API.

        Args:
            rendered_content: Rendered content (plain text or Markdown) to send.

        Returns:
            True if send was successful, False otherwise.

        """
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": self._settings.telegram_chat_id,
                        "text": rendered_content,
                        "parse_mode": "Markdown",
                    },
                )
                response.raise_for_status()

            logger.info("Telegram message sent successfully", event="telegram_sent")
            return True

        except httpx.TimeoutException:
            logger.warning(
                "Telegram timeout",
                event="telegram_timeout",
                error_code="TELEGRAM_TIMEOUT",
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.error(
                "Telegram HTTP error",
                event="telegram_http_error",
                error_code="TELEGRAM_HTTP_STATUS",
                status_code=e.response.status_code,
            )
            return False
        except httpx.NetworkError:
            logger.error(
                "Telegram network error",
                event="telegram_network_error",
                error_code="TELEGRAM_NETWORK_ERROR",
            )
            return False
        except Exception as e:
            logger.error(
                "Telegram send failed with unexpected error",
                event="telegram_unexpected_error",
                error_code="TELEGRAM_UNEXPECTED_ERROR",
                error_type=type(e).__name__,
            )
            return False


__all__ = ["TelegramSender"]
