"""
DeliveryRouter — 信号推送路由器.

将 TradeIntent 列表渲染为通知消息，通过 NotificationPort 推送。
实现 SignalDeliveryProtocol，可注入到 SignalSnapshotProcess。

App 层仅定义 NotificationPort Protocol，具体通知实现在 Interfaces 层注入。
"""

from __future__ import annotations

import logging
from typing import Any

from ditto_app.types import TradeIntent

logger = logging.getLogger(__name__)

__all__ = ["DeliveryRouter", "NotificationPort"]


class NotificationPort:
    """通知发送协议 — App 层定义，Interfaces 层注入 AlertManager 适配器."""

    def send(
        self,
        template: str,
        context: dict[str, Any],
        level: str,
    ) -> dict[str, bool]:
        """发送通知，返回各通道成功/失败映射."""
        ...


class DeliveryRouter:
    """信号推送路由器 — 将 TradeIntent 渲染为通知消息."""

    def __init__(self, sender: NotificationPort | None = None) -> None:
        self._sender = sender

    def deliver(
        self,
        strategy_id: str,
        intents: list[TradeIntent],
        signal_date: str,
    ) -> dict[str, bool]:
        """推送信号通知（fire-and-forget）."""
        if not intents:
            return {}
        if self._sender is None:
            return {}
        context = self._build_context(strategy_id, intents, signal_date)
        try:
            return self._sender.send("signal_delivery", context, "info")
        except Exception:
            logger.exception(
                "Signal delivery failed (fire-and-forget)",
                extra={"strategy_id": strategy_id, "signal_date": signal_date},
            )
            return {}

    def send_signal(self, strategy_id: str, intents: list[TradeIntent]) -> None:
        """SignalDeliveryProtocol 实现 — 从 intents 推断 signal_date."""
        signal_date = intents[0].signal_date if intents else ""
        self.deliver(strategy_id, intents, signal_date)

    def render_markdown(
        self,
        strategy_id: str,
        intents: list[TradeIntent],
        signal_date: str,
    ) -> str:
        """渲染 Markdown 格式信号内容."""
        if not intents:
            return ""
        buys = [i for i in intents if i.direction == "buy"]
        sells = [i for i in intents if i.direction == "sell"]
        lines = [
            f"## Signal: {strategy_id}",
            f"**Date**: {signal_date}",
            (
                f"**Buy**: {len(buys)}"
                f" | **Sell**: {len(sells)}"
                f" | **Total**: {len(intents)}"
            ),
            "",
        ]
        for intent in intents:
            direction = intent.direction.upper()
            lines.append(
                f"- {direction} #{intent.instrument_id}"
                + f" (delta={intent.delta_weight:+.4f})"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_context(
        strategy_id: str,
        intents: list[TradeIntent],
        signal_date: str,
    ) -> dict[str, Any]:
        """构建通知上下文."""
        buys = [i for i in intents if i.direction == "buy"]
        sells = [i for i in intents if i.direction == "sell"]
        return {
            "strategy_id": strategy_id,
            "signal_date": signal_date,
            "buy_count": len(buys),
            "sell_count": len(sells),
            "total_intents": len(intents),
            "intents": [
                {
                    "instrument_id": i.instrument_id,
                    "direction": i.direction,
                    "delta_weight": round(i.delta_weight, 4),
                }
                for i in intents
            ],
        }
