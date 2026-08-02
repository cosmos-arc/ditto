"""Shared fail-closed contracts for research backtest service construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)

from ditto_application.exceptions import AppProcessError


def backtest_construction_error(reason: str, **details: object) -> AppProcessError:
    """Return the stable reproducibility failure used by graph verification."""
    return AppProcessError(
        "frozen research backtest construction failed",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


@dataclass(frozen=True, slots=True)
class KnowledgeLagRuleProvider:
    """Apply the audit's calendar-day knowledge fence to verified PIT rules."""

    inner: InMemoryRuleProvider
    knowledge_lag_days: int

    def _as_of(self, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise backtest_construction_error(
                "invalid_rule_query_date", as_of_date=value
            ) from None
        return (parsed - timedelta(days=self.knowledge_lag_days)).isoformat()

    def get_definition(
        self, instrument_id: InstrumentId
    ) -> InstrumentDefinition | None:
        """Return the static definition bound to the verified artifact."""
        return self.inner.get_definition(instrument_id)

    def get_trading_rule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> TradingRuleSet | None:
        """Resolve only rules known by the lagged decision cutoff."""
        return self.inner.get_trading_rule(instrument_id, self._as_of(as_of_date))

    def get_fee_schedule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> FeeSchedule | None:
        """Resolve only fees known by the lagged decision cutoff."""
        return self.inner.get_fee_schedule(instrument_id, self._as_of(as_of_date))

    def get_rules(
        self,
        as_of_date: str,
        instrument_ids: list[InstrumentId],
    ) -> dict[InstrumentId, InstrumentRules]:
        """Resolve an exact rule batch at the lagged decision cutoff."""
        return self.inner.get_rules(self._as_of(as_of_date), instrument_ids)


@dataclass(frozen=True, slots=True)
class KnowledgeLagRulesGetter:
    """Exact callable binding brokerage lookups to one lag-aware provider."""

    provider: KnowledgeLagRuleProvider

    def __call__(self, instrument_id: InstrumentId, trade_date: str) -> InstrumentRules:
        """Return complete rules or fail closed without a fallback provider."""
        resolved = self.provider.get_rules(trade_date, [instrument_id])
        rules = resolved.get(instrument_id)
        if rules is None:
            raise backtest_construction_error(
                "frozen_instrument_rules_missing",
                instrument_id=int(instrument_id),
                trade_date=trade_date,
            )
        return rules
