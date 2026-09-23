"""Formal paper-session use-case dependency injection."""

from __future__ import annotations

from datetime import UTC, datetime

from dishka import Provider, Scope, provide
from ditto_execution.paper.session import PaperSessionStorePort
from ditto_portfolio.account_ledger import AccountEventJournalPort

from ditto_application.commands.paper_account import CreatePaperAccountHandler
from ditto_application.commands.paper_session import PaperSessionCommandHandler
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperSession,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_application.queries.account_catalog import (
    ListPaperAccountsQuery,
    ListPaperSessionsQuery,
)
from ditto_application.queries.paper_session import GetPaperSessionQuery

__all__ = ["AppPaperProvider"]


class AppPaperProvider(Provider):
    """Bind formal paper application services to execution-owned ports."""

    scope = Scope.APP

    @provide
    def create_paper_account_handler(
        self,
        account_journal: AccountEventJournalPort,
    ) -> CreatePaperAccountHandler:
        """Build recoverable PAPER account bootstrap commands."""
        return CreatePaperAccountHandler(
            journal=account_journal,
            clock=lambda: datetime.now(UTC),
        )

    @provide
    def paper_reconciler(
        self,
        store: PaperSessionStorePort,
        account_journal: AccountEventJournalPort,
    ) -> ReconcilePaperAccount:
        """Build the EOD reconciliation process."""
        return ReconcilePaperAccount(
            store=store,
            account_journal=account_journal,
        )

    @provide
    def paper_command_handler(
        self,
        store: PaperSessionStorePort,
        account_journal: AccountEventJournalPort,
        reconciler: ReconcilePaperAccount,
    ) -> PaperSessionCommandHandler:
        """Build idempotent paper account and session commands."""
        return PaperSessionCommandHandler(
            store=store,
            account_journal=account_journal,
            clock=lambda: datetime.now(UTC),
            reconciler=reconciler,
        )

    @provide
    def operate_paper_session(
        self,
        store: PaperSessionStorePort,
        account_journal: AccountEventJournalPort,
    ) -> OperatePaperSession:
        """Build crash-safe paper operation orchestration."""
        return OperatePaperSession(store=store, account_journal=account_journal)

    @provide
    def get_paper_session_query(
        self,
        store: PaperSessionStorePort,
    ) -> GetPaperSessionQuery:
        """Build the exact paper-session query facade."""
        return GetPaperSessionQuery(store=store)

    @provide
    def paper_accounts_query(
        self,
        account_journal: AccountEventJournalPort,
    ) -> ListPaperAccountsQuery:
        """List PAPER accounts for pickers without hand-typed identifiers."""
        return ListPaperAccountsQuery(journal=account_journal)

    @provide
    def paper_sessions_query(
        self,
        store: PaperSessionStorePort,
    ) -> ListPaperSessionsQuery:
        """List one account's paper sessions for pickers."""
        return ListPaperSessionsQuery(store=store)
