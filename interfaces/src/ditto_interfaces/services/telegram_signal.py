"""
Telegram 信号推送实现 — SignalDeliveryProtocol 的具体实现.

通过 Telegram Bot API 推送交易信号通知。
信号推送为 best-effort，失败时仅记录日志不抛出异常。
"""

from __future__ import annotations

import httpx
from ditto_app.types import TradeIntent
from loguru import logger

__all__ = ["TelegramSignalDelivery"]


class TelegramSignalDelivery:
    """
    基于 Telegram Bot API 的信号推送实现.

    Args:
        bot_token: Telegram Bot Token.
        chat_id: 目标聊天 ID.

    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send_signal(self, strategy_id: str, intents: list[TradeIntent]) -> None:
        """
        推送信号通知到 Telegram.

        Best-effort 推送，失败时仅记录日志，不抛出异常。
        """
        if not intents:
            return

        text = self._build_message(strategy_id, intents)
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
                resp.raise_for_status()
                logger.info(
                    "telegram_signal_sent",
                    strategy_id=strategy_id,
                    intent_count=len(intents),
                )
        except httpx.HTTPError:
            logger.exception(
                "telegram_signal_delivery_failed",
                strategy_id=strategy_id,
                intent_count=len(intents),
            )

    @staticmethod
    def _build_message(strategy_id: str, intents: list[TradeIntent]) -> str:
        """构建 Telegram 消息文本."""
        lines = [
            f"<b>Strategy Signal: {strategy_id}</b>",
            f"Intents: {len(intents)}",
            "",
        ]
        for i, intent in enumerate(intents, 1):
            qty_str = str(intent.quantity) if intent.quantity is not None else "-"
            detail = f"| delta={intent.delta_weight:+.4f} | qty={qty_str}"
            lines.append(
                f"{i}. {intent.instrument_id} | {intent.direction} {detail}",
            )
        return "\n".join(lines)
