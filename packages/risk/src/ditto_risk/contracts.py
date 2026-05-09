"""Risk domain contracts — Protocol definitions for risk consumers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting import AccountView

from ditto_risk.post_trade import RiskAction

__all__ = ["PostTradeGuard", "RiskSlice"]


class RiskSlice(Protocol):
    """盘后风控扫描所需的最小市场切片."""

    @property
    def bars(self) -> dict[InstrumentId, Any]:
        """当前 bar 数据，按 instrument_id 索引."""
        ...


@runtime_checkable
class PostTradeGuard(Protocol):
    """盘后风控扫描接口 — 检查账户状态并返回风控动作."""

    def scan(self, account_view: AccountView, slice_: RiskSlice) -> list[RiskAction]:
        """扫描账户状态，返回触发的风控动作列表."""
        ...

    def reset(self) -> None:
        """重置风控扫描状态."""
        ...
