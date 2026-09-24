"""Exact fixed-target Paper handoff identities and resolved facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_application.paper_contracts import (
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)


@dataclass(frozen=True)
class ETFPaperHandoffRequest:
    """Exact target, account, PIT and retry identity for one handoff."""

    allocation_id: str
    version_id: str
    authorization_id: str
    account_id: str
    session_id: str
    idempotency_key: str
    signal_date: str
    decision_date: str
    intended_trade_date: str
    knowledge_cutoff: datetime
    source_snapshot_id: str
    ledger_cutoff: datetime | None = None


@dataclass(frozen=True)
class ETFPaperHandoffFacts:
    """Trusted, PIT-bound ETF reference and Paper account facts."""

    signal_date: str
    knowledge_cutoff: datetime
    source_snapshot_id: str
    current_positions: dict[int, float]
    investable_instrument_ids: frozenset[int]
    signal_ledger_hash: str


class ETFPaperHandoffFactsPort(Protocol):
    """Resolve current account and instrument facts without caller claims."""

    def resolve(self, request: ETFPaperHandoffRequest) -> ETFPaperHandoffFacts:
        """Return exact handoff facts or fail closed."""
        ...


@dataclass(frozen=True)
class ETFPaperExecutionRequest:
    """One exact, after-market evaluation of a pre-approved ETF Paper target."""

    allocation_id: str
    version_id: str
    authorization_id: str
    account_id: str
    session_id: str
    signal_date: str
    intended_trade_date: str
    execution_cutoff: datetime
    reference_snapshot_id: str
    market_snapshot_id: str
    idempotency_key: str


@dataclass(frozen=True)
class ETFPaperOrderFacts:
    """PIT signal-day sizing facts and independently checked execution-day facts."""

    signal_nav: float
    signal_cash_available: float
    signal_current_quantity: int
    signal_available_quantity: int
    signal_reference_price: float
    signal_rules: PaperInstrumentRulesInput
    signal_ledger_hash: str
    execution_cash_available: float
    execution_position_quantity: int
    execution_available_quantity: int
    execution_rules: PaperInstrumentRulesInput
    execution_market: PaperMarketSnapshotInput
    settlement_date: str
    execution_ledger_hash: str


class ETFPaperExecutionFactsPort(Protocol):
    """Read only exact retained, admitted market and account evidence."""

    def resolve(
        self,
        request: ETFPaperExecutionRequest,
        *,
        instrument_id: int,
        signal_snapshot_id: str,
        signal_cutoff: datetime,
        valuation_cutoff: datetime,
    ) -> ETFPaperOrderFacts:
        """Return exact signal and execution facts or fail closed."""
        ...
