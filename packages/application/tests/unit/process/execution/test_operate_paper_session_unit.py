"""PAP-04: crash-safe and idempotent formal paper session operation."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
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
from ditto_portfolio.account_ledger import AccountDefinition, AccountKind

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
        position_quantity=0,
        available_quantity=0,
    )


def _seed(database: Path) -> None:
    with SqliteAccountEventJournal(str(database)) as journal:
        journal.create_account(
            AccountDefinition(
                account_id="paper-account-1",
                kind=AccountKind.PAPER,
                name="Paper Account",
                opened_at=NOW,
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
        assert journal.list_events("paper-account-1") == ()

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
        assert len(events) == 1
        assert events[0].source.value == "paper_engine"
        assert events[0].event_type.value == "buy"
        assert events[0].external_reference == recovered.execution.execution_id

        replayed = OperatePaperSession(
            store=recovered_store,
            account_journal=recovered_journal,
        ).execute(command)
        assert replayed.status == "replayed"
        assert len(recovered_store.list_executions("paper-session-1")) == 1
        assert len(recovered_journal.list_events("paper-account-1")) == 1


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
