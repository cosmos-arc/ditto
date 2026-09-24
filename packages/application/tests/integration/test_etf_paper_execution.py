"""ETF fixed target reaches the real Paper execution and ledger stores once."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_application.etf_paper_contracts import (
    ETFPaperExecutionRequest,
    ETFPaperOrderFacts,
)
from ditto_application.etf_paper_execution import ETFPaperExecution
from ditto_application.exceptions import AppCommandError, AppConflictError
from ditto_application.execution_dto import TradeIntent
from ditto_application.paper_contracts import (
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperSession,
)
from ditto_application.processes.execution.signal_package_models import SignalPackage
from ditto_execution.paper.session import PaperSession, PaperSessionStatus
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_portfolio.account_ledger import AccountDefinition, AccountKind

SIGNAL = datetime(2026, 9, 1, 7, 10, tzinfo=UTC)
EXECUTION = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)


def _request() -> ETFPaperExecutionRequest:
    return ETFPaperExecutionRequest(
        allocation_id="demo",
        version_id="version-a",
        authorization_id="authorization-a",
        account_id="paper-a",
        session_id="session-a",
        signal_date="2026-09-01",
        intended_trade_date="2026-09-02",
        execution_cutoff=EXECUTION,
        reference_snapshot_id="reference-exec",
        market_snapshot_id="market-exec",
        idempotency_key="execute-once",
    )


def _rules() -> PaperInstrumentRulesInput:
    return PaperInstrumentRulesInput(
        asset_class="etf",
        exchange="XSHG",
        tick_size=0.001,
        lot_size=100,
        board_segment="fund",
        settlement_cycle=1,
        commission_rate=0.0003,
        min_commission=5,
        stamp_duty_rate=0,
        transfer_fee_rate=0,
    )


def _facts() -> ETFPaperOrderFacts:
    return ETFPaperOrderFacts(
        signal_nav=100_000,
        signal_cash_available=100_000,
        signal_current_quantity=0,
        signal_available_quantity=0,
        signal_reference_price=10,
        signal_rules=_rules(),
        signal_ledger_hash="ledger-before",
        execution_cash_available=100_000,
        execution_position_quantity=0,
        execution_available_quantity=0,
        execution_rules=_rules(),
        execution_market=PaperMarketSnapshotInput(
            dataset_id="etf_daily",
            source="recorded",
            source_snapshot_id="market-exec",
            observed_at=EXECUTION,
            publication_cutoff=EXECUTION,
            open=10.0,
            high=10.2,
            low=9.9,
            close=10.1,
            prev_close=10.0,
            volume=1_000_000.0,
            amount=10_000_000.0,
            limit_up=11.0,
            limit_down=9.0,
        ),
        settlement_date="2026-09-03",
    )


def _package() -> SignalPackage:
    return SignalPackage(
        run_id="eod-2026-09-01-etf-allocation:demo-version-a",
        strategy_id="etf-allocation:demo",
        signal_date="2026-09-01",
        intents=(
            TradeIntent(
                intent_id="intent-a",
                strategy_id="etf-allocation:demo",
                signal_date="2026-09-01",
                instrument_id=1,
                direction="buy",
                target_weight=0.5,
                current_weight=0,
                delta_weight=0.5,
            ),
        ),
        dataset_snapshot_ids={
            "etf_reference": "reference-signal",
            "etf_research_reference": "reference-signal",
            "paper_signal_ledger": "ledger-before",
        },
        factor_ids=(),
        risk_flags=(),
        factor_values={},
        selection_reasons={},
        checksum="sha256:package",
        artifact_id="package-a",
        artifact_status="active",
    )


def _seed(path: Path) -> None:
    with SqliteAccountEventJournal(str(path)) as journal:
        journal.create_account(
            AccountDefinition(
                account_id="paper-a",
                kind=AccountKind.PAPER,
                name="Paper A",
                opened_at=SIGNAL,
            )
        )
    with SqlitePaperSessionStore(str(path)) as sessions:
        sessions.create_session(
            PaperSession(
                session_id="session-a",
                account_id="paper-a",
                strategy_id="etf-allocation:demo",
                trade_date="2026-09-02",
                status=PaperSessionStatus.RUNNING,
                revision=1,
                created_at=SIGNAL,
                updated_at=SIGNAL,
            )
        )


def _process(
    sessions: SqlitePaperSessionStore,
    journal: SqliteAccountEventJournal,
    facts: MagicMock,
) -> ETFPaperExecution:
    allocations = MagicMock()
    allocations.authorized_paper_version.return_value = SimpleNamespace(
        asof="2026-09-01",
        knowledge_cutoff=SIGNAL.isoformat(),
        source_snapshot_id="reference-signal",
    )
    packages = MagicMock()
    packages.find_active_paper.return_value = _package()
    return ETFPaperExecution(
        allocations=allocations,
        packages=packages,
        sessions=sessions,
        facts=facts,
        operator=OperatePaperSession(store=sessions, account_journal=journal),
    )


def test_etf_paper_fill_replays_without_a_second_ledger_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "paper.db"
    _seed(path)
    facts = MagicMock()
    facts.resolve.return_value = _facts()
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        process = _process(sessions, journal, facts)
        first = process.execute(_request())
        assert len(first) == 1
        assert first[0].status == "filled"
        assert first[0].ledger_event_id is not None
        assert len(journal.list_events("paper-a")) == 1
        second = process.execute(_request())
        assert second == first
        assert len(journal.list_events("paper-a")) == 1
        assert len(sessions.list_executions("session-a")) == 1
        paused = sessions.get_session("session-a")
        assert paused is not None
        monkeypatch.setattr(
            sessions,
            "get_session",
            lambda _: paused.pause(updated_at=EXECUTION, reason="review"),
        )
        assert process.execute(_request()) == first
        with pytest.raises(AppConflictError, match="payload conflict"):
            process.execute(
                ETFPaperExecutionRequest(
                    **{
                        **_request().__dict__,
                        "market_snapshot_id": "different-market",
                    }
                )
            )


def test_etf_paper_rejects_preclose_execution(tmp_path: Path) -> None:
    path = tmp_path / "paper.db"
    _seed(path)
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        process = _process(sessions, journal, MagicMock())
        with pytest.raises(AppCommandError, match="market close"):
            process.execute(
                ETFPaperExecutionRequest(
                    **{
                        **_request().__dict__,
                        "execution_cutoff": datetime(2026, 9, 2, 5, 0, tzinfo=UTC),
                    }
                )
            )
        assert sessions.list_executions("session-a") == ()
        assert journal.list_events("paper-a") == ()


def test_etf_paper_rejects_changed_signal_ledger_before_sizing(tmp_path: Path) -> None:
    path = tmp_path / "paper.db"
    _seed(path)
    facts = MagicMock()
    facts.resolve.return_value = ETFPaperOrderFacts(
        **{**_facts().__dict__, "signal_ledger_hash": "retroactive-change"}
    )
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        process = _process(sessions, journal, facts)
        with pytest.raises(AppConflictError, match="signal-day Paper ledger changed"):
            process.execute(_request())
        assert sessions.list_executions("session-a") == ()
        assert journal.list_events("paper-a") == ()
