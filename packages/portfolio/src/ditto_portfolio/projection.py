"""Portfolio state projection — 从 fill 流重建组合状态."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from ditto_kernel.identity import InstrumentId

from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.position import Position

__all__ = ["AccountProjector", "FillProjector", "PortfolioStateSnapshot"]


@dataclass(frozen=True)
class PortfolioStateSnapshot:
    """Portfolio 状态快照 — 从 fill 流可完整重建。"""

    positions: dict[InstrumentId, Position]
    cash: CashBook
    as_of_date: str | None = None


class FillProjector(Protocol):
    """从 fill 流重建 portfolio 状态的投影器。"""

    def project(self, fills: Iterable[FillEvent]) -> PortfolioStateSnapshot:
        """从 fill 流投影出 PortfolioStateSnapshot。"""
        ...


class AccountProjector:
    """基于 Account 的 FillProjector 实现。"""

    def __init__(self, initial_cash: CashBook | None = None) -> None:
        cash = initial_cash or CashBook(available=0.0, settled=0.0, frozen=0.0)
        self._account = Account(cash=cash)

    def project(self, fills: Iterable[FillEvent]) -> PortfolioStateSnapshot:
        """从 fill 流重建 portfolio 状态快照。"""
        for fill in fills:
            self._account.apply_fill(fill, settle_date="1970-01-01")
        view = self._account.get_view()
        return PortfolioStateSnapshot(
            positions=dict(view.positions),
            cash=view.cash,
        )
