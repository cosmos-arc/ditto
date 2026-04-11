"""
人工执行闭环 — Port 定义.

app 层定义 Port Protocol，interfaces 层提供具体实现。
遵循依赖倒置原则：app 层声明需要什么能力，interfaces 层注入实现。
"""

from __future__ import annotations

from typing import Protocol

from ditto_app.process.execution.types import TradeIntent

__all__ = [
    "PositionReader",
    "SignalDeliveryProtocol",
]


# ===========================================================================
# PositionReader — 读取当前实际持仓
# ===========================================================================


class PositionReader(Protocol):
    """
    读取当前实际持仓.

    从持仓快照或交易系统获取当前持仓权重映射。
    interfaces 层实现此 Protocol 并注入 SignalSnapshotProcess。
    """

    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        """获取策略当前持仓权重映射 (instrument_id -> weight)."""
        ...


# ===========================================================================
# SignalDeliveryProtocol — 信号推送协议
# ===========================================================================


class SignalDeliveryProtocol(Protocol):
    """
    信号推送协议 — app 层定义，interfaces 层实现.

    推送交易信号通知（如 Telegram / 邮件 / Webhook）。
    可选依赖，不注入时不影响 generate_intents 逻辑。
    """

    def send_signal(self, strategy_id: str, intents: list[TradeIntent]) -> None:
        """推送信号通知."""
        ...
