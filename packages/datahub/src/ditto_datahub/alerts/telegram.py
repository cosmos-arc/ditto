"""Telegram bot alert sender."""

import os

import httpx
from ditto_foundation import logger

from ditto_datahub.alerts.base import AlertMessage, AlertSender


class TelegramAlertSender(AlertSender):
    """Telegram bot alert sender."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        """
        Initialize Telegram alert sender.

        Args:
            bot_token: Telegram bot token. If None, reads from TELEGRAM_BOT_TOKEN env var.
            chat_id: Telegram chat ID. If None, reads from TELEGRAM_CHAT_ID env var.

        """
        self._bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

        if not self._bot_token or not self._chat_id:
            logger.warning(
                "Telegram not configured",
                event="telegram_not_configured",
            )

    @property
    def name(self) -> str:
        return "telegram"

    def send(self, message: AlertMessage) -> bool:
        """Send alert to Telegram."""
        if not self._bot_token or not self._chat_id:
            logger.warning(
                "Telegram alert skipped (not configured)",
                event="telegram_skipped",
                title=message.title,
            )
            return False

        try:
            formatted = message.format()
            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": formatted,
                "parse_mode": "Markdown",
            }

            response = httpx.post(url, json=payload, timeout=10)
            response.raise_for_status()

            logger.debug(
                "Telegram alert sent",
                event="telegram_sent",
                title=message.title,
            )
            return True

        except Exception as e:
            logger.error(
                "Telegram alert failed",
                event="telegram_error",
                title=message.title,
                error=str(e),
            )
            return False
