"""Risk domain contracts — Protocol definitions for risk consumers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_risk.post_trade import RiskAction

__all__ = ["PostTradeGuard"]


@runtime_checkable
class PostTradeGuard(Protocol):
    """盘后风控扫描接口 — 检查账户状态并返回风控动作."""

    def scan(self, account_view: object, context: object) -> list[RiskAction]:
        """扫描账户状态，返回触发的风控动作列表."""
        ...

    def reset(self) -> None:
        """重置风控扫描状态."""
        ...
