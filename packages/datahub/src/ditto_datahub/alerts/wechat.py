"""WeChat enterprise bot alert sender."""

import os
from typing import Any

import httpx
from ditto_foundation import logger

from ditto_datahub.alerts.base import AlertLevel, AlertMessage, AlertSender


class WeChatAlertSender(AlertSender):
    """WeChat enterprise bot alert sender."""

    def __init__(self, webhook_url: str | None = None) -> None:
        """
        Initialize WeChat alert sender.

        Args:
            webhook_url: WeChat bot webhook URL. If None, reads from
                WECHAT_WEBHOOK_URL env var.

        """
        self._webhook_url = webhook_url or os.getenv("WECHAT_WEBHOOK_URL")
        if not self._webhook_url:
            logger.warning(
                "WeChat webhook URL not configured",
                event="wechat_not_configured",
            )

    @property
    def name(self) -> str:
        """Sender name."""
        return "wechat"

    def send(self, message: AlertMessage) -> bool:
        """Send alert to WeChat."""
        if not self._webhook_url:
            logger.warning(
                "WeChat alert skipped (no webhook URL)",
                event="wechat_skipped",
                title=message.title,
            )
            return False

        try:
            formatted = message.format()
            payload = {
                "msgtype": "text",
                "text": {
                    "content": formatted,
                },
            }

            response = httpx.post(
                self._webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()

            logger.debug(
                "WeChat alert sent",
                event="wechat_sent",
                title=message.title,
                status_code=response.status_code,
            )
            return True

        except Exception as e:
            logger.error(
                "WeChat alert failed",
                event="wechat_error",
                title=message.title,
                error=str(e),
            )
            return False
