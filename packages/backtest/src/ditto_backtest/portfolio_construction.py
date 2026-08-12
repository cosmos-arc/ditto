"""Consumer-owned portfolio construction port for the backtest runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_execution.targets import TargetPortfolioLike
from ditto_portfolio.accounting import AccountView

__all__ = [
    "PortfolioConstructionContext",
    "PortfolioConstructionOutcome",
    "PortfolioConstructor",
]


@dataclass(frozen=True)
class PortfolioConstructionContext:
    """Explicit PIT/account inputs visible to a backtest construction provider."""

    trade_date: str
    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    candidate_target: TargetPortfolioLike
    account_view: AccountView


@dataclass(frozen=True)
class PortfolioConstructionOutcome:
    """Constructed target or structured fail-closed evidence."""

    success: bool
    target_portfolio: TargetPortfolioLike | None
    evidence: Mapping[str, object]
    failure_code: str | None = None
    failure_message: str | None = None

    @classmethod
    def completed(
        cls,
        *,
        target_portfolio: TargetPortfolioLike,
        evidence: Mapping[str, object],
    ) -> PortfolioConstructionOutcome:
        """Build a successful construction outcome."""
        return cls(
            success=True,
            target_portfolio=target_portfolio,
            evidence=dict(evidence),
        )

    @classmethod
    def failed(
        cls,
        *,
        code: str,
        message: str,
        evidence: Mapping[str, object],
    ) -> PortfolioConstructionOutcome:
        """Build a structured construction failure."""
        return cls(
            success=False,
            target_portfolio=None,
            evidence=dict(evidence),
            failure_code=code,
            failure_message=message,
        )


class PortfolioConstructor(Protocol):
    """Provider contract consumed by the backtest portfolio step."""

    def construct(
        self,
        context: PortfolioConstructionContext,
    ) -> PortfolioConstructionOutcome:
        """Construct a target from the candidate and explicit PIT context."""
        ...
