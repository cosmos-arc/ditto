"""Consumer-owned continuous risk port for deterministic backtests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ditto_execution.orders.model import Order
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting import AccountView, FillEvent
from ditto_risk.pre_trade import PreTradeContext

__all__ = [
    "BacktestRiskContext",
    "BacktestRiskDecision",
    "BacktestRiskRuntime",
    "DailyRiskOutcome",
]


@dataclass(frozen=True)
class BacktestRiskContext:
    """Authoritative inputs supplied at one backtest risk boundary."""

    trade_date: str
    account_view: AccountView
    bars: Mapping[InstrumentId, MarketSnapshot]
    pre_trade_context: PreTradeContext | None = None


@dataclass(frozen=True)
class BacktestRiskDecision:
    """Binary pre-trade decision with an optional resized order."""

    allow: bool
    adjusted_order: Order | None
    reason_code: str | None = None
    reason: str | None = None
    triggered_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyRiskOutcome:
    """Daily readiness result used to stop the chain fail closed."""

    readiness: str
    block_reasons: tuple[str, ...]
    evidence: Mapping[str, object]


class BacktestRiskRuntime(Protocol):
    """Continuous gate lifecycle supplied by application orchestration."""

    def daily_scan(self, context: BacktestRiskContext) -> DailyRiskOutcome:
        """Scan the authoritative start-of-step account state."""
        ...

    def pre_trade(
        self,
        order: Order,
        context: BacktestRiskContext,
    ) -> BacktestRiskDecision:
        """Allow, resize, or reject an order before brokerage submission."""
        ...

    def post_fill(
        self,
        fill: FillEvent,
        context: BacktestRiskContext,
        event_id: str,
    ) -> None:
        """Apply one fill idempotently after authoritative accounting."""
        ...

    def snapshot_state_json(self) -> str:
        """Return canonical versioned state for a checkpoint."""
        ...

    def restore_state_json(
        self,
        payload_json: str,
        account_view: AccountView,
    ) -> None:
        """Restore verified state against the current authoritative account."""
        ...
