"""
SignalDelivery 组件注册 (DI Provider).

提供 NotificationPort 的具体实现：
- Telegram 通道：将通知上下文渲染为 HTML 消息推送
- NoOp 通道：未配置时静默跳过

DeliveryRouter 注入 NotificationPort 后，作为 SignalDeliveryProtocol 实现。
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from dishka import Provider, Scope, provide
from ditto_app.process.execution.delivery import DeliveryRouter, NotificationPort
from ditto_app.process.execution.ports import SignalDeliveryProtocol
from ditto_infra.foundation import logger

__all__ = ["SignalDeliveryProvider"]

_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"


class _TelegramNotificationAdapter(NotificationPort):
    """Telegram 通知适配器 — 将 NotificationPort.send() 转为 Telegram Bot API 调用."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(
        self,
        template: str,
        context: dict[str, Any],
        level: str,
    ) -> dict[str, bool]:
        """发送 Telegram 通知，返回通道成功/失败映射."""
        text = self._build_html(context)
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
            return {"telegram": True}
        except httpx.HTTPError:
            logger.exception(
                "telegram_notification_failed",
                template=template,
                level=level,
            )
            return {"telegram": False}

    @staticmethod
    def _build_html(context: dict[str, Any]) -> str:
        """从通知上下文构建 Telegram HTML 消息."""
        lines = [
            f"<b>Signal: {context.get('strategy_id', '?')}</b>",
            f"Date: {context.get('signal_date', '?')}",
            (
                f"Buy: {context.get('buy_count', 0)}"
                f" | Sell: {context.get('sell_count', 0)}"
                f" | Total: {context.get('total_intents', 0)}"
            ),
            "",
        ]
        for intent in context.get("intents", []):
            direction = str(intent.get("direction", "?")).upper()
            iid = intent.get("instrument_id", "?")
            delta = float(intent.get("delta_weight", 0))
            lines.append(f"- {direction} #{iid} (delta={delta:+.4f})")
        return "\n".join(lines)


class _NoOpNotificationPort(NotificationPort):
    """未配置 Telegram 时的空实现 — 不执行任何推送."""

    def send(
        self,
        template: str,
        context: dict[str, Any],
        level: str,
    ) -> dict[str, bool]:
        """No-op: 不推送."""
        return {}


class SignalDeliveryProvider(Provider):
    """
    SignalDelivery Provider — 通知端口 + 推送路由 + 信号协议.

    依赖链:
      SignalDeliveryProvider → NotificationPort
      → DeliveryRouter → SignalDeliveryProtocol

    - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 均配置时 → Telegram
    - 否则 → NoOp
    """

    scope = Scope.APP

    @provide
    def notification_port(self) -> NotificationPort:
        """提供通知端口实现."""
        bot_token = os.environ.get(_BOT_TOKEN_ENV, "").strip()
        chat_id = os.environ.get(_CHAT_ID_ENV, "").strip()

        if not bot_token or not chat_id:
            logger.info(
                "notification_port_noop",
                reason="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured",
            )
            return _NoOpNotificationPort()

        logger.info("notification_port_telegram", chat_id=chat_id)
        return _TelegramNotificationAdapter(bot_token=bot_token, chat_id=chat_id)

    @provide
    def delivery_router(
        self,
        sender: NotificationPort,
    ) -> DeliveryRouter:
        """信号推送路由器 — 注入 NotificationPort."""
        return DeliveryRouter(sender=sender)

    @provide
    def signal_delivery(
        self,
        router: DeliveryRouter,
    ) -> SignalDeliveryProtocol:
        """DeliveryRouter 实现 SignalDeliveryProtocol — 注入 SignalSnapshotProcess."""
        return router
