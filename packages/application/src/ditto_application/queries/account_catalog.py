"""
Read-only account and paper-session catalogs for entity pickers.

The comparison workspace needs to offer MANUAL/PAPER accounts and their
paper sessions without hand-typed internal identifiers; these queries are
plain deterministic reads over the journal and session stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_execution.paper.session import PaperSessionStorePort
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventJournalPort,
    AccountKind,
)

__all__ = [
    "AccountCatalogEntryView",
    "ListManualAccountsQuery",
    "ListPaperAccountsQuery",
    "ListPaperSessionsQuery",
    "PaperSessionCatalogEntryView",
]


@dataclass(frozen=True, kw_only=True)
class AccountCatalogEntryView:
    """One selectable account identity."""

    account_id: str
    account_kind: str
    account_name: str
    currency: str
    opened_at: datetime


@dataclass(frozen=True, kw_only=True)
class PaperSessionCatalogEntryView:
    """One selectable paper session bound to one PAPER account."""

    session_id: str
    account_id: str
    strategy_id: str
    trade_date: str
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime


def _entry(account: AccountDefinition) -> AccountCatalogEntryView:
    return AccountCatalogEntryView(
        account_id=account.account_id,
        account_kind=account.kind.value,
        account_name=account.name,
        currency=account.currency,
        opened_at=account.opened_at,
    )


class ListManualAccountsQuery:
    """List MANUAL accounts in deterministic id order."""

    def __init__(self, *, journal: AccountEventJournalPort) -> None:
        self._journal = journal

    def list(self) -> tuple[AccountCatalogEntryView, ...]:
        """Return every MANUAL account; an empty catalog is a valid answer."""
        return tuple(
            _entry(account)
            for account in self._journal.list_accounts()
            if account.kind is AccountKind.MANUAL
        )


class ListPaperAccountsQuery:
    """List PAPER accounts in deterministic id order."""

    def __init__(self, *, journal: AccountEventJournalPort) -> None:
        self._journal = journal

    def list(self) -> tuple[AccountCatalogEntryView, ...]:
        """Return every PAPER account; an empty catalog is a valid answer."""
        return tuple(
            _entry(account)
            for account in self._journal.list_accounts()
            if account.kind is AccountKind.PAPER
        )


class ListPaperSessionsQuery:
    """List one account's paper sessions in deterministic trade-date order."""

    def __init__(self, *, store: PaperSessionStorePort) -> None:
        self._store = store

    def list(self, account_id: str) -> tuple[PaperSessionCatalogEntryView, ...]:
        """Return the account's sessions; an unknown account simply has none."""
        return tuple(
            PaperSessionCatalogEntryView(
                session_id=session.session_id,
                account_id=session.account_id,
                strategy_id=session.strategy_id,
                trade_date=session.trade_date,
                status=session.status.value,
                revision=session.revision,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in self._store.list_sessions(account_id)
        )
