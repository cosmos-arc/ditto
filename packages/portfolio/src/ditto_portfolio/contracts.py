"""Portfolio domain contracts — Protocol definitions for portfolio consumers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_portfolio.accounting.account import AccountView

__all__ = ["PortfolioStateReader"]


@runtime_checkable
class PortfolioStateReader(Protocol):
    """组合状态读取接口 — 提供只读账户快照."""

    def get_view(self) -> AccountView:
        """返回当前账户状态快照."""
        ...
