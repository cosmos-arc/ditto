"""Daily decision cockpit query facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ditto_application.execution_dto import ActualPositionSnapshot, TradeIntent
from ditto_application.queries.deviation import (
    SignalDeviationQueryFacade,
    SignalDeviationReport,
)
from ditto_application.queries.portfolio_actual import (
    PnlSummary,
    PortfolioActualQueryFacade,
)
from ditto_application.queries.signal import SignalQueryFacade

__all__ = ["DailyDecisionQueryFacade", "DailyDecisionReport"]

DailyDecisionReadinessStatus = Literal["ready", "blocked", "review"]


@dataclass(frozen=True)
class DailyDecisionReport:
    """Read model for one daily trading decision review."""

    strategy_id: str
    trade_date: str | None
    readiness_status: DailyDecisionReadinessStatus
    readiness_reasons: tuple[str, ...]
    signal_intents: tuple[TradeIntent, ...]
    deviation: SignalDeviationReport | None
    positions: tuple[ActualPositionSnapshot, ...]
    pnl: PnlSummary | None


class DailyDecisionQueryFacade:
    """Compose the daily cockpit read model from existing query facades."""

    def __init__(
        self,
        *,
        signal_facade: SignalQueryFacade,
        portfolio_facade: PortfolioActualQueryFacade,
        deviation_facade: SignalDeviationQueryFacade,
    ) -> None:
        self._signal_facade = signal_facade
        self._portfolio_facade = portfolio_facade
        self._deviation_facade = deviation_facade

    def get_report(
        self,
        *,
        strategy_id: str,
        trade_date: str | None = None,
    ) -> DailyDecisionReport:
        """Return the daily decision report for a strategy/date."""
        signal_intents = self._get_signal_intents(
            strategy_id=strategy_id,
            trade_date=trade_date,
        )
        resolved_trade_date = trade_date or _latest_signal_date(signal_intents)
        if resolved_trade_date is None or not signal_intents:
            return DailyDecisionReport(
                strategy_id=strategy_id,
                trade_date=resolved_trade_date,
                readiness_status="blocked",
                readiness_reasons=("no signal intents available",),
                signal_intents=(),
                deviation=None,
                positions=(),
                pnl=None,
            )

        positions = tuple(
            self._portfolio_facade.get_position_history(
                strategy_id,
                snapshot_date=resolved_trade_date,
            )
        )
        deviation = self._deviation_facade.get_deviation(
            strategy_id=strategy_id,
            signal_date=resolved_trade_date,
        )
        pnl = self._portfolio_facade.compute_pnl(
            strategy_id,
            resolved_trade_date,
        )
        readiness_reasons = _readiness_reasons(
            signal_intents=signal_intents,
            positions=positions,
        )
        return DailyDecisionReport(
            strategy_id=strategy_id,
            trade_date=resolved_trade_date,
            readiness_status=_readiness_status(readiness_reasons),
            readiness_reasons=readiness_reasons,
            signal_intents=tuple(signal_intents),
            deviation=deviation,
            positions=positions,
            pnl=pnl,
        )

    def _get_signal_intents(
        self,
        *,
        strategy_id: str,
        trade_date: str | None,
    ) -> list[TradeIntent]:
        if trade_date is None:
            return self._signal_facade.get_latest_intents(strategy_id)
        return self._signal_facade.get_intents_by_date(
            strategy_id=strategy_id,
            signal_date=trade_date,
        )


def _latest_signal_date(intents: list[TradeIntent]) -> str | None:
    if not intents:
        return None
    return max(intent.signal_date for intent in intents)


def _readiness_reasons(
    *,
    signal_intents: list[TradeIntent],
    positions: tuple[ActualPositionSnapshot, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not signal_intents:
        reasons.append("no signal intents available")
    if not positions:
        reasons.append("positions unavailable for trade date")
    return tuple(reasons)


def _readiness_status(
    readiness_reasons: tuple[str, ...],
) -> DailyDecisionReadinessStatus:
    if not readiness_reasons:
        return "ready"
    if "no signal intents available" in readiness_reasons:
        return "blocked"
    return "review"
