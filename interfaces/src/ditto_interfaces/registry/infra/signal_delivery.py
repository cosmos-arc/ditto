"""
SignalDelivery 组件注册 (DI Provider).

提供 TelegramSignalDelivery 作为 SignalDeliveryProtocol 的具体实现。
当环境变量未配置时，提供 no-op 空实现。
"""

from __future__ import annotations

import os

from dishka import Provider, Scope, provide
from ditto_app.process.execution.ports import SignalDeliveryProtocol
from ditto_infra.foundation import logger

from ditto_interfaces.services.telegram_signal import TelegramSignalDelivery

__all__ = ["SignalDeliveryProvider"]

_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"  # noqa: S105
_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"


class _NoOpSignalDelivery:
    """未配置 Telegram 时的空实现 — 不执行任何推送."""

    def send_signal(self, strategy_id: str, intents: list) -> None:  # type: ignore[type-arg]
        """No-op: 不推送信号."""


class SignalDeliveryProvider(Provider):
    """
    SignalDelivery Provider — 根据环境变量决定注入实现.

    - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 均配置时 → TelegramSignalDelivery
    - 否则 → _NoOpSignalDelivery
    """

    scope = Scope.APP

    @provide
    def signal_delivery(self) -> SignalDeliveryProtocol:
        """提供信号推送实现."""
        bot_token = os.environ.get(_BOT_TOKEN_ENV, "").strip()
        chat_id = os.environ.get(_CHAT_ID_ENV, "").strip()

        if not bot_token or not chat_id:
            logger.info(
                "signal_delivery_noop",
                reason="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured",
            )
            return _NoOpSignalDelivery()

        logger.info("signal_delivery_telegram", chat_id=chat_id)
        return TelegramSignalDelivery(bot_token=bot_token, chat_id=chat_id)
