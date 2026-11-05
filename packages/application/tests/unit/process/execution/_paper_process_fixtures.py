"""Shared seeding for generic-path paper process unit tests."""

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
)
from ditto_execution.paper.session import PaperSession, PaperSessionStatus
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)

NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def generic_buy_command() -> OperatePaperOrderCommand:
    """One board-lot BUY against the seeded account and session."""
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


def seed_paper_account_and_session(
    database: Path,
    *,
    opening_cash: str = "100000",
) -> None:
    """Create the PAPER account (with opening cash) and its running session."""
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
                    gross_amount=Decimal(opening_cash),
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


def append_cash_event(
    database: Path,
    *,
    event_type: AccountEventType,
    event_id: str,
    idempotency_key: str,
    amount: Decimal,
) -> None:
    """Append one arbitrary cash event straight to the journal."""
    with SqliteAccountEventJournal(str(database)) as journal:
        account = journal.get_account("paper-account-1")
        assert account is not None
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=event_type,
                    event_id=event_id,
                    trade_date="2026-08-31",
                    settlement_date="2026-08-31",
                    recorded_at=NOW,
                    idempotency_key=idempotency_key,
                    actor="paper-engine:account-bootstrap",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=amount,
                ),
            )
        )
