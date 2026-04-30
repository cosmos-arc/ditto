"""
DeliveryRouter — 信号推送路由器.

将 TradeIntent 列表渲染为通知上下文，通过 AlertManager 多通道推送。
实现 SignalDeliveryProtocol，可注入到 SignalSnapshotProcess。
"""

from __future__ import annotations

from typing import Any

from ditto_platform.services.notification import NotificationLevel
from ditto_platform.services.notification.manager import AlertManager
from loguru import logger

from ditto_app.execution_dto import TradeIntent

__all__ = ["DeliveryRouter"]


class DeliveryRouter:
    """信号推送路由器 — 将 TradeIntent 渲染为通知消息，通过 AlertManager 推送."""

    def __init__(self, alert_manager: AlertManager | None = None) -> None:
        self._alert_manager = alert_manager

    def deliver(
        self,
        strategy_id: str,
        intents: list[TradeIntent],
        signal_date: str,
    ) -> dict[str, bool]:
        """推送信号通知（fire-and-forget）."""
        if not intents:
            return {}
        if self._alert_manager is None:
            return {}
        context = self._build_context(strategy_id, intents, signal_date)
        try:
            return self._alert_manager.send_alert(
                "signal_trading", context, NotificationLevel.INFO
            )
        except (OSError, ConnectionError, TimeoutError):
            logger.error(
                "Signal delivery failed, strategy_id={}, signal_date={}",
                strategy_id,
                signal_date,
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
            "actions": [
                {
                    "instrument_id": i.instrument_id,
                    "action": i.direction,
                    "current_weight": round(i.current_weight, 4),
                    "target_weight": round(i.target_weight, 4),
                    "delta_weight": round(i.delta_weight, 4),
                }
                for i in intents
            ],
        }
