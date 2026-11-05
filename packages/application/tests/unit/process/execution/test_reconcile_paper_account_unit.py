"""Reverse-direction reconciliation for PAPER session ledger facts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ditto_application.paper_contracts import (
    PaperFillAssumptionInput,
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperOrderCommand,
    OperatePaperSession,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_execution.paper.session import PaperSession, PaperSessionStatus
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)

NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _command() -> OperatePaperOrderCommand:
    return OperatePaperOrderCommand(
        session_id="paper-session-1",
        idempotency_key="paper-operation-1",
        order_id="paper-order-1",
        instrument_id=600519,
        side="buy",
        order_type="market",
        quantity=100,
        price=None,
        trade_date="2026-08-31",
        market=PaperMarketSnapshotInput(
            dataset_id="a-share-daily-bars",
            source="tushare",
            source_snapshot_id="snapshot-20260831-600519",
            observed_at=NOW,
            publication_cutoff=NOW,
            open=9.8,
            high=10.2,
            low=9.7,
            close=10.0,
            prev_close=9.9,
            volume=1_000_000.0,
            amount=10_000_000.0,
            limit_up=10.89,
            limit_down=8.91,
        ),
        rules=PaperInstrumentRulesInput(
            asset_class="stock",
            exchange="XSHG",
            tick_size=0.01,
            lot_size=100,
            board_segment="main",
            settlement_cycle=1,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        ),
        assumption=PaperFillAssumptionInput(
            assumption_id="paper-default-v1",
            version=1,
            reference_price_field="close",
            slippage_bps=1.0,
        ),
        decision_at=NOW,
        execution_at=NOW,
        settlement_date="2026-09-01",
    )


def _seed(database: Path) -> None:
    account = AccountDefinition(
        account_id="paper-account-1",
        kind=AccountKind.PAPER,
        name="Paper Account",
        opened_at=NOW,
    )
    with SqliteAccountEventJournal(str(database)) as journal:
        journal.create_account(account)
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.OPENING_CASH,
                    event_id="account-event:opening",
                    trade_date="2026-08-31",
                    settlement_date="2026-08-31",
                    recorded_at=NOW,
                    idempotency_key="paper-opening:test",
                    actor="paper-engine:account-bootstrap",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=Decimal("100000"),
                ),
            )
        )
    with SqlitePaperSessionStore(str(database)) as store:
        store.create_session(
            PaperSession(
                session_id="paper-session-1",
                account_id="paper-account-1",
                strategy_id="strategy-1",
                trade_date="2026-08-31",
                status=PaperSessionStatus.RUNNING,
                revision=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )


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
