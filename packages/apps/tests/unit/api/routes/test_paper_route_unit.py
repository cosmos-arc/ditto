"""PAP-06 formal paper API workflow and OpenAPI contracts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch

from ditto_application.commands.paper_account import CreatePaperAccountHandler
from ditto_application.commands.paper_session import PaperSessionCommandHandler
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperSession,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.paper_session import GetPaperSessionQuery
from ditto_apps.api.routes.paper import (
    create_paper_account,
    create_paper_session,
    get_paper_account_ledger,
    get_paper_session,
    operate_paper_order,
    pause_paper_session,
    reconcile_paper_session,
    recover_paper_session,
)
from ditto_apps.models.paper import (
    CreatePaperAccountBody,
    CreatePaperSessionBody,
    OperatePaperOrderBody,
    PaperFillAssumptionBody,
    PaperInstrumentRulesBody,
    PaperMarketSnapshotBody,
    PausePaperSessionBody,
    ReconcilePaperSessionBody,
    RecoverPaperSessionBody,
)
from ditto_apps.openapi_contract import create_openapi_app
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal

NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


async def _inline(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


def _original(function: Callable[..., object]) -> Callable[..., object]:
    return cast(Callable[..., object], function.__dict__["__dishka_orig_func__"])


def _operate_body() -> OperatePaperOrderBody:
    return OperatePaperOrderBody(
        idempotency_key="operate-1",
        order_id="paper-order-1",
        instrument_id=600519,
        side="buy",
        order_type="market",
        quantity=100,
        trade_date=date(2026, 8, 31),
        settlement_date=date(2026, 9, 1),
        decision_at=NOW,
        execution_at=NOW,
        position_quantity=0,
        available_quantity=0,
        market=PaperMarketSnapshotBody(
            dataset_id="a-share-daily-bars",
            source="tushare",
            source_snapshot_id="snapshot-1",
            observed_at=NOW,
            publication_cutoff=NOW,
            open=9.8,
            high=10.2,
            low=9.7,
            close=10.0,
            prev_close=9.9,
            volume=1_000_000,
            amount=10_000_000,
            limit_up=10.89,
            limit_down=8.91,
        ),
        rules=PaperInstrumentRulesBody(
            asset_class="stock",
            exchange="XSHG",
            tick_size=0.01,
            lot_size=100,
            board_segment="main",
            settlement_cycle=1,
            commission_rate=0.0003,
            min_commission=5,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        ),
        assumption=PaperFillAssumptionBody(
            assumption_id="paper-default-v1",
            version=1,
            reference_price_field="close",
            slippage_bps=1,
        ),
    )


def test_paper_request_models_accept_standard_json_wire_values() -> None:
    """FastAPI validates decoded JSON, so ISO dates and decimal strings must work."""
    account = CreatePaperAccountBody(
        account_id="paper-account-1",
        name="Main Paper",
        opened_at=NOW,
        trade_date=date(2026, 8, 31),
        initial_cash=Decimal("100000"),
        idempotency_key="paper-account-create-1",
    )
    session = CreatePaperSessionBody(
        session_id="paper-session-1",
        account_id="paper-account-1",
        strategy_id="strategy-1",
        trade_date=date(2026, 8, 31),
        idempotency_key="paper-session-create-1",
    )
    execution = _operate_body()

    assert (
        CreatePaperAccountBody.model_validate(account.model_dump(mode="json"))
        == account
    )
    assert (
        CreatePaperSessionBody.model_validate(session.model_dump(mode="json"))
        == session
    )
    assert (
        OperatePaperOrderBody.model_validate(execution.model_dump(mode="json"))
        == execution
    )


def test_paper_routes_complete_local_workflow(tmp_path: Path) -> None:
    database = str(tmp_path / "paper-api.sqlite")
    journal = SqliteAccountEventJournal(database)
    store = SqlitePaperSessionStore(database)
    reconciler = ReconcilePaperAccount(store=store, account_journal=journal)
    session_handler = PaperSessionCommandHandler(
        store=store,
        account_journal=journal,
        clock=lambda: NOW,
        reconciler=reconciler,
    )
    account_handler = CreatePaperAccountHandler(journal=journal, clock=lambda: NOW)
    operator = OperatePaperSession(store=store, account_journal=journal)
    query = GetPaperSessionQuery(store=store)

    with patch("ditto_apps.api.routes.paper.asyncio.to_thread", side_effect=_inline):
        account = asyncio.run(
            _original(create_paper_account)(
                body=CreatePaperAccountBody(
                    account_id="paper-account-1",
                    name="Main Paper",
                    opened_at=NOW,
                    trade_date=date(2026, 8, 31),
                    initial_cash=Decimal("100000"),
                    idempotency_key="paper-account-create-1",
                ),
                handler=account_handler,
            )
        )
        session = asyncio.run(
            _original(create_paper_session)(
                body=CreatePaperSessionBody(
                    session_id="paper-session-1",
                    account_id="paper-account-1",
                    strategy_id="strategy-1",
                    trade_date=date(2026, 8, 31),
                    idempotency_key="paper-session-create-1",
                    start_immediately=True,
                ),
                handler=session_handler,
            )
        )
        execution = asyncio.run(
            _original(operate_paper_order)(
                session_id="paper-session-1",
                body=_operate_body(),
                process=operator,
            )
        )
        ledger = asyncio.run(
            _original(get_paper_account_ledger)(
                account_id="paper-account-1",
                as_of=date(2026, 8, 31),
                query=AccountLedgerQuery(journal=journal),
            )
        )
        read = asyncio.run(
            _original(get_paper_session)(
                session_id="paper-session-1",
                query=query,
            )
        )
        reconciliation = asyncio.run(
            _original(reconcile_paper_session)(
                session_id="paper-session-1",
                body=ReconcilePaperSessionBody(idempotency_key="eod-1"),
                handler=session_handler,
            )
        )
        paused = asyncio.run(
            _original(pause_paper_session)(
                session_id="paper-session-1",
                body=PausePaperSessionBody(
                    idempotency_key="pause-1",
                    reason="EOD complete",
                ),
                handler=session_handler,
            )
        )
        recovered = asyncio.run(
            _original(recover_paper_session)(
                session_id="paper-session-1",
                body=RecoverPaperSessionBody(idempotency_key="recover-1"),
                process=operator,
            )
        )

    assert account.data.account_kind == "paper"
    assert account.data.opening_event_id is not None
    assert session.data.session.status == "running"
    assert execution.data.status == "created"
    assert execution.data.fill is not None
    assert execution.data.ledger_event_id is not None
    assert ledger.data.account.account_kind == "paper"
    assert len(ledger.data.events) == 2
    assert len(read.data.executions) == 1
    assert reconciliation.data.balanced is True
    assert reconciliation.data.fill_count == 1
    assert reconciliation.data.ledger_fill_count == 1
    assert paused.data.session.status == "paused"
    assert recovered.data.recovered_execution_count == 1
    store.close()
    journal.close()


def test_paper_openapi_surface_has_stable_operation_ids() -> None:
    schema = create_openapi_app().openapi()
    expected = {
        "/api/v1/paper/accounts": "paper_create_account",
        "/api/v1/paper/accounts/{account_id}/ledger": "paper_get_account_ledger",
        "/api/v1/paper/sessions": "paper_create_session",
        "/api/v1/paper/sessions/{session_id}": "paper_get_session",
        "/api/v1/paper/sessions/{session_id}/orders": "paper_operate_order",
        "/api/v1/paper/sessions/{session_id}/pause": "paper_pause_session",
        "/api/v1/paper/sessions/{session_id}/reconcile": "paper_reconcile_session",
        "/api/v1/paper/sessions/{session_id}/recover": "paper_recover_session",
    }
    for path, operation_id in expected.items():
        operations = schema["paths"][path]
        assert operation_id in {
            operation["operationId"] for operation in operations.values()
        }
