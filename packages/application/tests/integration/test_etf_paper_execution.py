"""ETF fixed target reaches the real Paper execution and ledger stores once."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.etf_paper_contracts import (
    ETFPaperExecutionRequest,
    ETFPaperOrderFacts,
)
from ditto_application.etf_paper_execution import ETFPaperExecution
from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppProcessError,
)
from ditto_application.execution_dto import TradeIntent
from ditto_application.paper_contracts import (
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperSession,
)
from ditto_application.processes.execution.signal_package_models import SignalPackage
from ditto_apps.api.routes.portfolio_comparison import router
from ditto_apps.middleware import configure_exception_handlers
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
    ledger_hash,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def _facts(
    execution_ledger_hash: str = "ledger-stale",
) -> ETFPaperOrderFacts:
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
        execution_ledger_hash=execution_ledger_hash,
    )


def _live_facts(journal: SqliteAccountEventJournal) -> MagicMock:
    """Fake facts whose execution ledger hash tracks the real journal stream."""
    facts = MagicMock()

    def resolve(
        request: ETFPaperExecutionRequest, *, instrument_id: int, **_: object
    ) -> ETFPaperOrderFacts:
        return _facts(
            execution_ledger_hash=ledger_hash(journal.list_events(request.account_id))
        )

    facts.resolve.side_effect = resolve
    return facts


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
            "paper_signal_reference_cutoff": SIGNAL.isoformat(),
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
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        process = _process(sessions, journal, _live_facts(journal))
        first = process.execute(_request())
        assert len(first) == 1
        assert first[0].status == "filled"
        assert first[0].ledger_event_id is not None
        resolve = process._facts.resolve.call_args.kwargs
        assert resolve["signal_snapshot_id"] == "reference-signal"
        assert resolve["signal_cutoff"] == SIGNAL
        assert resolve["valuation_cutoff"] == SIGNAL
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
        assert (
            process.execute(
                ETFPaperExecutionRequest(
                    **{**_request().__dict__, "market_snapshot_id": "new-evidence"}
                )
            )
            == first
        )
        assert len(journal.list_events("paper-a")) == 1


def test_etf_paper_execution_cutoff_may_follow_next_day_bar_availability(
    tmp_path: Path,
) -> None:
    """Daily bars are stamped knowledge_date = trade_date + 1 by the producer."""
    path = tmp_path / "paper.db"
    _seed(path)
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        process = _process(sessions, journal, _live_facts(journal))
        outcomes = process.execute(
            replace(
                _request(),
                execution_cutoff=datetime(2026, 9, 3, 8, tzinfo=UTC),
            )
        )
        assert outcomes[0].status == "filled"
        assert len(journal.list_events("paper-a")) == 1


def test_etf_paper_rejects_package_without_pinned_valuation_cutoff(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper.db"
    _seed(path)
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        process = _process(sessions, journal, _live_facts(journal))
        package = _package()
        process._packages.find_active_paper.return_value = replace(
            package,
            dataset_snapshot_ids={
                key: value
                for key, value in package.dataset_snapshot_ids.items()
                if key != "paper_signal_reference_cutoff"
            },
        )
        with pytest.raises(AppConflictError, match="valuation cutoff"):
            process.execute(_request())
        assert sessions.list_executions("session-a") == ()
        assert journal.list_events("paper-a") == ()


def test_etf_rejected_attempt_reevaluates_with_corrected_evidence(
    tmp_path: Path,
) -> None:
    """A deferred/rejected record has no ledger effect and must not lock the intent."""
    path = tmp_path / "paper.db"
    _seed(path)
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        facts = MagicMock()

        def resolve(
            request: ETFPaperExecutionRequest, *, instrument_id: int, **_: object
        ) -> ETFPaperOrderFacts:
            base = _facts(
                execution_ledger_hash=ledger_hash(journal.list_events("paper-a"))
            )
            if request.market_snapshot_id == "market-rejected":
                return replace(
                    base,
                    execution_market=replace(
                        base.execution_market,
                        source_snapshot_id="market-rejected",
                        open=10.8,
                        high=11.0,
                        low=10.7,
                        close=11.0,
                        limit_up=11.0,
                    ),
                )
            return replace(
                base,
                execution_market=replace(
                    base.execution_market, source_snapshot_id="market-fixed"
                ),
            )

        facts.resolve.side_effect = resolve
        process = _process(sessions, journal, facts)
        rejected = process.execute(
            replace(_request(), market_snapshot_id="market-rejected")
        )
        assert rejected[0].status == "deferred"
        assert rejected[0].reason == "limit_up_no_buy"
        assert journal.list_events("paper-a") == ()

        filled = process.execute(replace(_request(), market_snapshot_id="market-fixed"))
        assert filled[0].status == "filled"
        assert filled[0].ledger_event_id is not None
        assert len(journal.list_events("paper-a")) == 1
        assert len(sessions.list_executions("session-a")) == 1


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


def test_etf_partial_fill_recovers_with_new_evidence_for_pending_intent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper.db"
    _seed(path)
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        facts = MagicMock()

        def resolve(
            request: ETFPaperExecutionRequest, *, instrument_id: int, **_: object
        ) -> ETFPaperOrderFacts:
            if instrument_id == 2 and request.market_snapshot_id == "market-exec":
                raise AppProcessError("second bar is missing")
            base = _facts(
                execution_ledger_hash=ledger_hash(journal.list_events("paper-a"))
            )
            if request.market_snapshot_id == "market-corrected":
                return replace(
                    base,
                    execution_market=replace(
                        base.execution_market, source_snapshot_id="market-corrected"
                    ),
                )
            return base

        facts.resolve.side_effect = resolve
        process = _process(sessions, journal, facts)
        package = _package()
        process._packages.find_active_paper.return_value = replace(
            package,
            intents=(
                *package.intents,
                replace(
                    package.intents[0],
                    intent_id="intent-b",
                    instrument_id=2,
                    target_weight=0.3,
                ),
            ),
        )
        with pytest.raises(AppProcessError, match="second bar"):
            process.execute(_request())
        first = sessions.list_executions("session-a")
        assert len(first) == 1
        assert len(journal.list_events("paper-a")) == 1
        completed = process.execute(
            replace(_request(), market_snapshot_id="market-corrected")
        )
        assert [item.status for item in completed] == ["filled", "filled"]
        assert completed[0].execution_id == first[0].execution_id
        assert len(sessions.list_executions("session-a")) == 2
        assert len(journal.list_events("paper-a")) == 2


def test_etf_paper_http_reaches_real_execution_and_sqlite_ledger(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper.db"
    _seed(path)
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        process = _process(sessions, journal, _live_facts(journal))

        class TestProvider(Provider):
            scope = Scope.APP

            @provide
            def executor(self) -> ETFPaperExecution:
                return process

        app = FastAPI()
        configure_exception_handlers(app)
        setup_dishka(container=make_async_container(TestProvider()), app=app)
        app.include_router(router, prefix="/api/v1")
        endpoint = (
            "/api/v1/portfolio/etf-allocations/demo/versions/version-a/paper-executions"
        )
        body = {
            "authorization_id": "authorization-a",
            "account_id": "paper-a",
            "session_id": "session-a",
            "signal_date": "2026-09-01",
            "intended_trade_date": "2026-09-02",
            "execution_cutoff": EXECUTION.isoformat(),
            "reference_snapshot_id": "reference-exec",
            "market_snapshot_id": "market-exec",
        }
        with TestClient(app) as web:
            first = web.post(
                endpoint, json=body, headers={"Idempotency-Key": "execute-once"}
            )
            assert first.status_code == 201, first.text
            event_id = first.json()["data"]["outcomes"][0]["ledger_event_id"]
            assert event_id is not None
            retry = web.post(
                endpoint, json=body, headers={"Idempotency-Key": "execute-once"}
            )
            assert retry.status_code == 201, retry.text
            assert retry.json() == first.json()
        assert len(sessions.list_executions("session-a")) == 1
        assert [event.event_id for event in journal.list_events("paper-a")] == [
            event_id
        ]


def test_etf_paper_execution_conflicts_when_ledger_moves_after_facts(
    tmp_path: Path,
) -> None:
    """A concurrent append between facts read and fill CAS must fail closed."""
    path = tmp_path / "paper.db"
    _seed(path)
    with (
        SqlitePaperSessionStore(str(path)) as sessions,
        SqliteAccountEventJournal(str(path)) as journal,
    ):
        account = journal.get_account("paper-a")
        assert account is not None
        stale_hash = ledger_hash(journal.list_events("paper-a"))
        facts = MagicMock()
        facts.resolve.return_value = _facts(execution_ledger_hash=stale_hash)
        process = _process(sessions, journal, facts)
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_type=AccountEventType.DEPOSIT,
                    event_id="concurrent-fill",
                    trade_date="2026-09-02",
                    settlement_date="2026-09-02",
                    recorded_at=EXECUTION,
                    idempotency_key="concurrent-fill",
                    actor="paper-session:other",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=Decimal("1"),
                ),
            )
        )
        with pytest.raises(AppConflictError, match="ledger changed during execution"):
            process.execute(_request())
        assert sessions.list_executions("session-a") == ()
        assert len(journal.list_events("paper-a")) == 1

        process._facts = _live_facts(journal)
        outcome = process.execute(_request())
        assert outcome[0].status == "filled"
        assert len(journal.list_events("paper-a")) == 2
