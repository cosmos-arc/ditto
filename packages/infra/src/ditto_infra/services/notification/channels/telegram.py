"""Telegram 通知渠道."""

import httpx
from loguru import logger

from ditto_infra.services.notification.config import NotificationSettings
from ditto_infra.services.notification.sender import NotificationSender


class TelegramSender(NotificationSender):
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

        except httpx.TimeoutException as e:
            logger.warning(
                "Telegram timeout",
                event="telegram_timeout",
                error=str(e),
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.error(
                "Telegram HTTP error",
                event="telegram_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            return False
        except httpx.NetworkError as e:
            logger.error(
                "Telegram network error",
                event="telegram_network_error",
                error=str(e),
            )
            return False
        except Exception as e:
            # 未预期的错误应该抛出，让调用方处理
            logger.error(
                "Telegram send failed with unexpected error",
                event="telegram_unexpected_error",
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            raise


__all__ = ["TelegramSender"]
