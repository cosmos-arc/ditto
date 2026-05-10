"""Portfolio domain contracts — Protocol definitions for portfolio consumers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_portfolio.accounting.account import AccountView

__all__ = ["PortfolioStateReader"]


@runtime_checkable
class PortfolioStateReader(Protocol):
    """
    组合状态读取接口 — 提供只读账户快照.

    Reserved for future portfolio state persistence.
    当前唯一消费场景为类型标注预留；projection.py 通过 AccountProjector
    直接使用 Account，尚未通过此 Protocol 解耦持久化层。
    保留此 seam 供未来组合状态持久化接入。
    """

    def get_view(self) -> AccountView:
        """返回当前账户状态快照."""
        ...
