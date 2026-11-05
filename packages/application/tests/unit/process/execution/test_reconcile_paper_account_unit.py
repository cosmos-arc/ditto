"""Reverse-direction reconciliation for PAPER session ledger facts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperSession,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    create_account_event,
)

from ._paper_process_fixtures import generic_buy_command, seed_paper_account_and_session

NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _command():
    return generic_buy_command()


def _seed(database: Path) -> None:
    seed_paper_account_and_session(database)


def test_reconcile_flags_ledger_events_without_a_paired_execution(
    tmp_path: Path,
) -> None:
    database = tmp_path / "paper-reconcile.db"
    _seed(database)
    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        reconciler = ReconcilePaperAccount(store=store, account_journal=journal)
        operator = OperatePaperSession(store=store, account_journal=journal)
        receipt = operator.execute(_command())
        assert receipt.execution.fill is not None

        baseline = reconciler.reconcile(
            session_id="paper-session-1",
            idempotency_key="eod-1",
            reconciled_at=NOW,
        )
        assert baseline.balanced is True
        assert baseline.ledger_fill_count == 1

        # Orphan: a session-attributed ledger event whose execution never
        # existed in the store must break balance even though the forward
        # counts still match.
        account = journal.get_account("paper-account-1")
        assert account is not None
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.BUY,
                    event_id="account-event:orphan",
                    trade_date="2026-08-31",
                    settlement_date="2026-09-01",
                    recorded_at=NOW,
                    idempotency_key="paper-ledger:orphan",
                    actor="paper-session:paper-session-1",
                    source=AccountEventSource.PAPER_ENGINE,
                    instrument_id=InstrumentId(600519),
                    quantity=Decimal("100"),
                    price=Decimal("10"),
                    gross_amount=Decimal("1000"),
                    external_reference="paper-execution:never-persisted",
                ),
            )
        )
        flagged = reconciler.reconcile(
            session_id="paper-session-1",
            idempotency_key="eod-2",
            reconciled_at=NOW,
        )
        assert flagged.balanced is False
        assert flagged.fill_count == 1
        assert flagged.ledger_fill_count == 1
