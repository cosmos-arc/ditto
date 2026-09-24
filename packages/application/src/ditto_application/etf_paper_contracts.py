"""Exact fixed-target Paper handoff identities and resolved facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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


@dataclass(frozen=True)
class ETFPaperHandoffFacts:
    """Trusted, PIT-bound ETF reference and Paper account facts."""

    signal_date: str
    knowledge_cutoff: datetime
    source_snapshot_id: str
    current_positions: dict[int, float]
    investable_instrument_ids: frozenset[int]


class ETFPaperHandoffFactsPort(Protocol):
    """Resolve current account and instrument facts without caller claims."""

    def resolve(self, request: ETFPaperHandoffRequest) -> ETFPaperHandoffFacts:
        """Return exact handoff facts or fail closed."""
        ...
