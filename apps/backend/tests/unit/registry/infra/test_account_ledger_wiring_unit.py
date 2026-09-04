"""Composition-root wiring for the account-ledger storage port."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, make_container, provide
from ditto_application.commands.account_ledger import (
    CreateAccountHandler,
    ManualAccountCommandHandler,
)
from ditto_application.providers_account_ledger import AppAccountLedgerProvider
from ditto_application.queries.account_event_evidence import (
    AccountEventEvidenceQueryFacade,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_execution.di import ExecutionStorageProvider
from ditto_platform.foundation import SQLitePool
from ditto_portfolio.account_ledger import AccountEventJournalPort


class _TestSqliteProvider(Provider):
    scope = Scope.APP

    def __init__(self, database: Path) -> None:
        super().__init__()
        self._database = database

    @provide
    def sqlite_pool(self) -> Iterator[SQLitePool]:
        pool = SQLitePool(str(self._database))
        try:
            yield pool
        finally:
            pool.close_all()


def test_account_ledger_port_and_application_handlers_share_one_lifetime(
    tmp_path: Path,
) -> None:
    database = tmp_path / "metadata.sqlite"
    with make_container(
        _TestSqliteProvider(database),
        ExecutionStorageProvider(),
        AppAccountLedgerProvider(),
    ) as container:
        journal = container.get(AccountEventJournalPort)

        assert container.get(AccountEventJournalPort) is journal
        assert isinstance(container.get(CreateAccountHandler), CreateAccountHandler)
        assert isinstance(
            container.get(ManualAccountCommandHandler),
            ManualAccountCommandHandler,
        )
        assert isinstance(container.get(AccountLedgerQuery), AccountLedgerQuery)
        assert isinstance(
            container.get(AccountEventEvidenceQueryFacade),
            AccountEventEvidenceQueryFacade,
        )

    assert database.exists()
