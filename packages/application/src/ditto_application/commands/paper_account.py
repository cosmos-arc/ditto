"""Idempotent PAPER account creation with an immutable opening balance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256

from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventJournalPort,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    AccountLedgerError,
    create_account_event,
)

from ditto_application.exceptions import AppCommandError, AppConflictError

__all__ = [
    "CreatePaperAccountCommand",
    "CreatePaperAccountHandler",
    "PaperAccountCommandReceipt",
]


@dataclass(frozen=True, kw_only=True)
class CreatePaperAccountCommand:
    """Create a PAPER account and one positive opening-cash event."""

    account_id: str
    name: str
    opened_at: datetime
    trade_date: str
    initial_cash: Decimal
    idempotency_key: str
    currency: str = "CNY"


@dataclass(frozen=True, kw_only=True)
class PaperAccountCommandReceipt:
    """Exact account and opening-event creation receipt."""

    account_id: str
    account_kind: str
    name: str
    status: str
    opening_event_id: str | None


class CreatePaperAccountHandler:
    """Recoverably create a PAPER identity followed by its opening cash fact."""

    def __init__(
        self,
        *,
        journal: AccountEventJournalPort,
        clock: Callable[[], datetime],
    ) -> None:
        self._journal = journal
        self._clock = clock

    def handle(self, command: CreatePaperAccountCommand) -> PaperAccountCommandReceipt:
        """Create or exactly replay account identity and opening cash."""
        try:
            requested = AccountDefinition(
                account_id=command.account_id,
                kind=AccountKind.PAPER,
                name=command.name,
                opened_at=command.opened_at,
                currency=command.currency,
            )
            existing_account = self._journal.get_account(command.account_id)
            if existing_account is not None and existing_account != requested:
                raise AppConflictError("paper account immutable identity conflict")
            account = (
                existing_account
                if existing_account is not None
                else self._journal.create_account(requested)
            )
            event_key = f"paper-opening:{command.idempotency_key}"
            existing_event = self._journal.find_by_idempotency_key(
                command.account_id,
                event_key,
            )
            recorded_at = (
                existing_event.recorded_at
                if existing_event is not None
                else self._clock()
            )
            event_id = (
                existing_event.event_id
                if existing_event is not None
                else _opening_event_id(command.account_id, command.idempotency_key)
            )
            event = create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.OPENING_CASH,
                    event_id=event_id,
                    trade_date=command.trade_date,
                    settlement_date=command.trade_date,
                    recorded_at=recorded_at,
                    idempotency_key=event_key,
                    actor="paper-engine:account-bootstrap",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=command.initial_cash,
                ),
            )
        except AccountLedgerError as exc:
            raise AppCommandError(str(exc)) from exc
        if existing_event is not None:
            if existing_event.event_hash != event.event_hash:
                raise AppConflictError("paper account idempotency payload conflict")
            return PaperAccountCommandReceipt(
                account_id=account.account_id,
                account_kind=account.kind.value,
                name=account.name,
                status="replayed",
                opening_event_id=existing_event.event_id,
            )
        created = self._journal.append(event)
        return PaperAccountCommandReceipt(
            account_id=account.account_id,
            account_kind=account.kind.value,
            name=account.name,
            status="created",
            opening_event_id=created.event_id,
        )


def _opening_event_id(account_id: str, idempotency_key: str) -> str:
    digest = sha256(f"{account_id}\x00{idempotency_key}".encode()).hexdigest()
    return f"account-event:{digest[:32]}"
