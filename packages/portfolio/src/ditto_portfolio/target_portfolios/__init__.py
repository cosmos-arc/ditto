"""Target portfolios — 目标组合构建与管理。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

__all__ = ["TargetPortfolio", "TargetPortfolioStore"]


@dataclass(frozen=True)
class TargetPortfolio:
    """Desired portfolio weights produced for a trade date."""

    portfolio_id: str
    target_id: str
    strategy_id: str
    trade_date: str
    weights: dict[int, float] = field(default_factory=dict)
    cash_weight: float = 0.0


class TargetPortfolioStore(Protocol):
    """Persistence contract for target portfolio DTOs."""

    def save_target_portfolio(self, target: TargetPortfolio) -> None:
        """Persist one target portfolio."""
        ...

    def get_target_portfolio(self, target_id: str) -> TargetPortfolio | None:
        """Return one target portfolio by id."""
        ...

    def list_target_portfolios(
        self,
        portfolio_id: str,
        trade_date: str | None = None,
    ) -> list[TargetPortfolio]:
        """List target portfolios for a portfolio, optionally by date."""
        ...
