"""End-of-day reconciliation for formal PAPER execution and ledger facts."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256

import orjson
from ditto_execution.paper.session import (
    PaperReconciliation,
    PaperSessionStorePort,
)
from ditto_portfolio.account_ledger import AccountEventJournalPort

from ditto_application.exceptions import AppNotFoundError

__all__ = ["ReconcilePaperAccount"]


class ReconcilePaperAccount:
    """Compare every filled execution with its exact PAPER account event."""

    def __init__(
        self,
        *,
        store: PaperSessionStorePort,
        account_journal: AccountEventJournalPort,
    ) -> None:
        self._store = store
        self._account_journal = account_journal

    def reconcile(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        reconciled_at: datetime,
    ) -> PaperReconciliation:
        """Create or replay a checksum over exact execution and ledger facts."""
        session = self._store.get_session(session_id)
        if session is None:
            raise AppNotFoundError(f"paper session not found: {session_id}")
        reconciliation_id = _reconciliation_id(session_id, idempotency_key)
        existing = self._store.get_reconciliation(reconciliation_id)
        if existing is not None:
            return existing
        executions = self._store.list_executions(session_id)
        filled = tuple(
            record for record in executions if record.result.fill is not None
        )
        account_events = self._account_journal.list_events(session.account_id)
        events_by_id = {event.event_id: event for event in account_events}
        matched_hashes: list[str] = []
        for record in filled:
            event = (
                events_by_id.get(record.ledger_event_id)
                if record.ledger_event_id is not None
                else None
            )
            if event is not None and event.external_reference == record.execution_id:
                matched_hashes.append(event.event_hash)
        balanced = len(matched_hashes) == len(filled)
        checksum = _checksum(
            session_id=session_id,
            trade_date=session.trade_date,
            execution_hashes=tuple(record.request_hash for record in executions),
            event_hashes=tuple(matched_hashes),
            balanced=balanced,
        )
        reconciliation = PaperReconciliation(
            reconciliation_id=reconciliation_id,
            session_id=session_id,
            trade_date=session.trade_date,
            order_count=len(executions),
            fill_count=len(filled),
            ledger_fill_count=len(matched_hashes),
            balanced=balanced,
            checksum=checksum,
            reconciled_at=reconciled_at,
        )
        return self._store.append_reconciliation(reconciliation)


def _reconciliation_id(session_id: str, idempotency_key: str) -> str:
    digest = sha256(f"{session_id}\x00{idempotency_key}".encode()).hexdigest()
    return f"paper-reconciliation:{digest[:32]}"


def _checksum(
    *,
    session_id: str,
    trade_date: str,
    execution_hashes: tuple[str, ...],
    event_hashes: tuple[str, ...],
    balanced: bool,
) -> str:
    encoded = orjson.dumps(
        {
            "session_id": session_id,
            "trade_date": trade_date,
            "execution_hashes": execution_hashes,
            "event_hashes": event_hashes,
            "balanced": balanced,
        },
        option=orjson.OPT_SORT_KEYS,
    )
    return f"paper-eod:sha256:{sha256(encoded).hexdigest()}"
