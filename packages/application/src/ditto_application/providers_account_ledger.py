"""Account-ledger DI provider for commands and exact as-of queries."""

from __future__ import annotations

from datetime import UTC, datetime

from dishka import Provider, Scope, provide
from ditto_portfolio.account_ledger import AccountEventJournalPort

from ditto_application.commands.account_ledger import (
    CreateAccountHandler,
    ManualAccountCommandHandler,
)
from ditto_application.queries.account_event_evidence import (
    AccountEventEvidenceQueryFacade,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery

__all__ = ["AppAccountLedgerProvider"]


class AppAccountLedgerProvider(Provider):
    """Bind account journal use cases to their persistence-neutral port."""

    scope = Scope.APP

    @provide
    def create_account_handler(
        self,
        journal: AccountEventJournalPort,
    ) -> CreateAccountHandler:
        """Create permanently typed portfolio identities through the journal port."""
        return CreateAccountHandler(journal=journal)

    @provide
    def manual_account_command_handler(
        self,
        journal: AccountEventJournalPort,
    ) -> ManualAccountCommandHandler:
        """Append MANUAL events with host-derived UTC recording timestamps."""
        return ManualAccountCommandHandler(
            journal=journal,
            clock=lambda: datetime.now(UTC),
        )

    @provide
    def account_ledger_query(
        self,
        journal: AccountEventJournalPort,
    ) -> AccountLedgerQuery:
        """Expose exact as-of account rebuilds over the shared journal."""
        return AccountLedgerQuery(journal=journal)

    @provide
    def account_event_evidence_query(
        self,
        query: AccountLedgerQuery,
    ) -> AccountEventEvidenceQueryFacade:
        """Expose Manual Account facts only through the privacy-scoped facade."""
        return AccountEventEvidenceQueryFacade(query=query)
