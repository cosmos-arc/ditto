"""PAP-04: crash-safe and idempotent formal paper session operation."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ditto_application.exceptions import AppConflictError
from ditto_application.paper_contracts import (
    PaperFillAssumptionInput,
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperOrderCommand,
    OperatePaperSession,
)
from ditto_execution.paper.session import PaperSession, PaperSessionStatus
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    AccountLedgerRevisionConflict,
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


def _seed(database: Path, *, opening_cash: str = "100000") -> None:
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


def test_restart_recovers_ledger_without_duplicate_fill(tmp_path: Path) -> None:
    database = tmp_path / "paper-crash.db"
    _seed(database)
    command = _command()

    def crash_after_execution_persisted() -> None:
        raise RuntimeError("simulated process crash")

    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        process = OperatePaperSession(
            store=store,
            account_journal=journal,
            after_execution_persisted=crash_after_execution_persisted,
        )
        with pytest.raises(RuntimeError, match="simulated process crash"):
            process.execute(command)
        assert len(store.list_executions("paper-session-1")) == 1
        assert len(journal.list_events("paper-account-1")) == 1

    with (
        SqlitePaperSessionStore(str(database)) as recovered_store,
        SqliteAccountEventJournal(str(database)) as recovered_journal,
    ):
        recovered = OperatePaperSession(
            store=recovered_store,
            account_journal=recovered_journal,
        ).execute(command)
        assert recovered.status == "replayed"
        assert recovered.execution.ledger_event_id is not None
        assert len(recovered_store.list_executions("paper-session-1")) == 1
        events = recovered_journal.list_events("paper-account-1")
        assert len(events) == 2
        assert events[1].source.value == "paper_engine"
        assert events[1].event_type.value == "buy"
        assert events[1].external_reference == recovered.execution.execution_id

        replayed = OperatePaperSession(
            store=recovered_store,
            account_journal=recovered_journal,
        ).execute(command)
        assert replayed.status == "replayed"
        assert len(recovered_store.list_executions("paper-session-1")) == 1
        assert len(recovered_journal.list_events("paper-account-1")) == 2


def test_concurrent_fill_append_preserves_the_execution_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CAS loser must not discard a record the winner already ledgered."""
    database = tmp_path / "paper-race.db"
    _seed(database)
    command = _command()

    def crash_after_execution_persisted() -> None:
        raise RuntimeError("simulated process crash")

    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        process = OperatePaperSession(
            store=store,
            account_journal=journal,
            after_execution_persisted=crash_after_execution_persisted,
        )
        with pytest.raises(RuntimeError, match="simulated process crash"):
            process.execute(command)
        assert len(store.list_executions("paper-session-1")) == 1

        real_append = journal.append_if_revision

        def losing_view(
            event: AccountEvent,
            *,
            expected_ledger_hash: str,
        ) -> AccountEvent:
            real_append(event, expected_ledger_hash=expected_ledger_hash)
            raise AccountLedgerRevisionConflict("loser snapshot")

        monkeypatch.setattr(journal, "append_if_revision", losing_view)
        recovered = OperatePaperSession(store=store, account_journal=journal).execute(
            command
        )
        assert recovered.status == "replayed"
        assert recovered.execution.ledger_event_id is not None
        assert len(journal.list_events("paper-account-1")) == 2
        assert len(store.list_executions("paper-session-1")) == 1


def test_same_idempotency_key_with_changed_order_conflicts(tmp_path: Path) -> None:
    database = tmp_path / "paper-idempotency.db"
    _seed(database)
    original = _command()
    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        process = OperatePaperSession(store=store, account_journal=journal)
        process.execute(original)
        changed = replace(original, quantity=200)
        with pytest.raises(Exception, match="idempotency"):
            process.execute(changed)


def test_generic_paper_order_cannot_bypass_etf_target_checks(tmp_path: Path) -> None:
    database = tmp_path / "etf-bypass.db"
    _seed(database)
    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        session = store.get_session("paper-session-1")
        assert session is not None
        store.create_session(
            replace(
                session, session_id="etf-session", strategy_id="etf-allocation:demo"
            )
        )
        process = OperatePaperSession(store=store, account_journal=journal)
        with pytest.raises(Exception, match="execution-time target"):
            process.execute(replace(_command(), session_id="etf-session"))
        assert store.list_executions("etf-session") == ()


def test_generic_order_rejects_declared_account_facts(tmp_path: Path) -> None:
    database = tmp_path / "paper-facts.db"
    _seed(database)
    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        process = OperatePaperSession(store=store, account_journal=journal)
        with pytest.raises(AppConflictError, match="cannot declare account facts"):
            process.execute(replace(_command(), position_quantity=100))
        with pytest.raises(AppConflictError, match="cannot declare account facts"):
            process.execute(replace(_command(), available_quantity=100))
        with pytest.raises(AppConflictError, match="cannot declare account facts"):
            process.execute(replace(_command(), cash_available=1_000_000.0))
        assert store.list_executions("paper-session-1") == ()


def test_generic_order_derives_cash_from_the_ledger(tmp_path: Path) -> None:
    database = tmp_path / "paper-cash.db"
    _seed(database, opening_cash="500")
    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        process = OperatePaperSession(store=store, account_journal=journal)
        receipt = process.execute(_command())
        assert receipt.execution.reality_status == "rejected"
        assert receipt.execution.reason == "insufficient_cash"
        assert receipt.execution.fill is None


def test_generic_order_derives_position_and_t_plus_one_availability(
    tmp_path: Path,
) -> None:
    database = tmp_path / "paper-position.db"
    _seed(database)
    sell = replace(
        _command(),
        idempotency_key="paper-operation-2",
        order_id="paper-order-2",
        side="sell",
    )
    with (
        SqlitePaperSessionStore(str(database)) as store,
        SqliteAccountEventJournal(str(database)) as journal,
    ):
        process = OperatePaperSession(store=store, account_journal=journal)
        bought = process.execute(_command())
        assert bought.execution.fill is not None

        # The projected position (100) now backs the sell, but T+1 keeps the
        # same-day availability at zero, so the derived facts defer it.
        deferred = process.execute(sell)
        assert deferred.execution.reality_status == "deferred"
        assert deferred.execution.reason == "t_plus1_not_sellable"
        assert deferred.execution.fill is None
