"""PAP-06 formal paper API workflow and OpenAPI contracts."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
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
from ditto_application.queries.portfolio_history import GetPaperHistoryQuery
from ditto_apps.api.errors import UnprocessableEntityError
from ditto_apps.api.routes.paper import (
    create_paper_account,
    create_paper_session,
    get_paper_account_history,
    get_paper_account_ledger,
    get_paper_session,
    operate_paper_order,
    pause_paper_session,
    reconcile_paper_session,
    recover_paper_session,
)
from ditto_apps.errors import NotFoundError
from ditto_apps.models.paper import (
    CreatePaperAccountBody,
    CreatePaperSessionBody,
    OperatePaperOrderBody,
    PaperFillAssumptionBody,
    PaperHistoryQueryParams,
    PaperInstrumentRulesBody,
    PaperMarketSnapshotBody,
    PausePaperSessionBody,
    ReconcilePaperSessionBody,
    RecoverPaperSessionBody,
)
from ditto_apps.openapi_contract import create_openapi_app
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    FlowPosition,
    create_account_event,
    ledger_hash,
)

NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


async def _inline(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


def _original[T](
    function: Callable[..., Awaitable[T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    return cast(
        Callable[..., Coroutine[Any, Any, T]],
        function.__dict__["__dishka_orig_func__"],
    )


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


def test_paper_ledger_route_binds_reads_to_the_recorded_cutoff(tmp_path: Path) -> None:
    database = str(tmp_path / "paper-ledger-cutoff.sqlite")
    journal = SqliteAccountEventJournal(database)
    account_handler = CreatePaperAccountHandler(journal=journal, clock=lambda: NOW)

    with patch(
        "ditto_apps.api.routes.paper.asyncio.to_thread",
        side_effect=_inline,
    ):
        asyncio.run(
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
        bound = asyncio.run(
            _original(get_paper_account_ledger)(
                account_id="paper-account-1",
                as_of=date(2026, 8, 31),
                query=AccountLedgerQuery(journal=journal),
                recorded_through=NOW,
            )
        )
        with pytest.raises(
            UnprocessableEntityError, match="hides events recorded after the cutoff"
        ):
            asyncio.run(
                _original(get_paper_account_ledger)(
                    account_id="paper-account-1",
                    as_of=date(2026, 8, 31),
                    query=AccountLedgerQuery(journal=journal),
                    recorded_through=NOW - timedelta(minutes=1),
                )
            )

    assert bound.data.snapshot.cash.total == Decimal("100000")
    journal.close()


def test_paper_openapi_surface_has_stable_operation_ids() -> None:
    schema = create_openapi_app().openapi()
    expected = {
        "/api/v1/paper/accounts": "paper_list_accounts",
        "/api/v1/paper/accounts/{account_id}/ledger": "paper_get_account_ledger",
        "/api/v1/paper/accounts/{account_id}/history": "paper_get_account_history",
        "/api/v1/paper/accounts/{account_id}/sessions": "paper_list_account_sessions",
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


class _SnapshotReader:
    def __init__(self) -> None:
        self._snapshot = _history_snapshot()

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        snapshot = self._snapshot
        return snapshot if snapshot.snapshot_id == snapshot_id else None

    def get_observed_at(self, snapshot_id: str) -> datetime | None:
        del snapshot_id
        return None

    def get_predecessor(self, snapshot_id: str) -> str | None:
        del snapshot_id
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        del dataset_id, source, canonical_asset
        return ()


class _EmptyBars:
    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        del context, instrument_id, instrument_code
        return ()


def _history_snapshot() -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="paper-route-fixture",
            request_start="2026-08-31",
            request_end="2026-09-01",
            schema_version="market.stock_daily.v1",
            checksum="sha256:paper-route-bars",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="sha256:params",
            response_metadata=(("rows", "0"),),
            license_record_id="license:fixture",
            row_count=0,
            payload_uri="file:///tmp/paper-route-bars.parquet",
            payload_retained=True,
            created_at=NOW,
        )
    )


def _deposit(journal: SqliteAccountEventJournal, account_id: str) -> None:
    account = journal.get_account(account_id)
    if account is None:
        raise AssertionError("paper fixture account is missing")
    journal.append(
        create_account_event(
            account=account,
            draft=AccountEventDraft(
                event_type=AccountEventType.DEPOSIT,
                event_id="paper-history-deposit",
                trade_date="2026-09-01",
                settlement_date="2026-09-01",
                recorded_at=NOW,
                idempotency_key="paper-history-deposit",
                actor="paper-engine:account-topup",
                source=AccountEventSource.PAPER_ENGINE,
                gross_amount=Decimal("100"),
                flow_position=FlowPosition.START_OF_DAY,
            ),
        )
    )


def test_paper_history_route_replays_session_bound_series(tmp_path: Path) -> None:
    database = str(tmp_path / "paper-history.sqlite")
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
    history_query = GetPaperHistoryQuery(
        journal=journal,
        session_store=store,
        snapshot_reader=_SnapshotReader(),
        valuation_source=_EmptyBars(),
    )

    with patch("ditto_apps.api.routes.paper.asyncio.to_thread", side_effect=_inline):
        asyncio.run(
            _original(create_paper_account)(
                body=CreatePaperAccountBody(
                    account_id="paper-history-1",
                    name="历史模拟账户",
                    opened_at=NOW,
                    trade_date=date(2026, 8, 31),
                    initial_cash=Decimal("100"),
                    idempotency_key="paper-history-account-1",
                ),
                handler=account_handler,
            )
        )
        asyncio.run(
            _original(create_paper_session)(
                body=CreatePaperSessionBody(
                    session_id="paper-history-session-1",
                    account_id="paper-history-1",
                    strategy_id="strategy-1",
                    trade_date=date(2026, 8, 31),
                    idempotency_key="paper-history-session-1",
                    start_immediately=True,
                ),
                handler=session_handler,
            )
        )
        _deposit(journal, "paper-history-1")
        events = journal.list_events("paper-history-1")
        result = asyncio.run(
            _original(get_paper_account_history)(
                account_id="paper-history-1",
                params=PaperHistoryQueryParams(
                    session_id="paper-history-session-1",
                    start_date=date(2026, 8, 31),
                    end_date=date(2026, 9, 1),
                    knowledge_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                    publication_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                    source_snapshot_ids=(_history_snapshot().snapshot_id,),
                    ledger_event_count=len(events),
                    ledger_hash=ledger_hash(events),
                ),
                query=history_query,
            )
        )

    points = result.data.points
    assert [point.on_date for point in points] == ["2026-08-31", "2026-09-01"]
    assert [point.total_value for point in points] == [
        Decimal("100.00"),
        Decimal("200.00"),
    ]
    assert points[1].period_return == Decimal("0")
    assert result.data.result_id.startswith("paper-history:sha256:")
    assert result.data.method == "twr-linked-v1"
    assert result.data.valuation_policy_version == "account-valuation-stale-evidence-v1"
    store.close()
    journal.close()


def test_paper_history_route_rejects_session_account_conflict(tmp_path: Path) -> None:
    database = str(tmp_path / "paper-history-conflict.sqlite")
    journal = SqliteAccountEventJournal(database)
    store = SqlitePaperSessionStore(database)
    account_handler = CreatePaperAccountHandler(journal=journal, clock=lambda: NOW)
    session_handler = PaperSessionCommandHandler(
        store=store,
        account_journal=journal,
        clock=lambda: NOW,
        reconciler=ReconcilePaperAccount(store=store, account_journal=journal),
    )
    history_query = GetPaperHistoryQuery(
        journal=journal,
        session_store=store,
        snapshot_reader=_SnapshotReader(),
        valuation_source=_EmptyBars(),
    )

    with patch("ditto_apps.api.routes.paper.asyncio.to_thread", side_effect=_inline):
        for account_id, suffix in (
            ("paper-history-2", "2"),
            ("paper-history-3", "3"),
        ):
            asyncio.run(
                _original(create_paper_account)(
                    body=CreatePaperAccountBody(
                        account_id=account_id,
                        name=f"账户{suffix}",
                        opened_at=NOW,
                        trade_date=date(2026, 8, 31),
                        initial_cash=Decimal("100"),
                        idempotency_key=f"paper-history-account-{suffix}",
                    ),
                    handler=account_handler,
                )
            )
            asyncio.run(
                _original(create_paper_session)(
                    body=CreatePaperSessionBody(
                        session_id=f"paper-history-session-{suffix}",
                        account_id=account_id,
                        strategy_id="strategy-1",
                        trade_date=date(2026, 8, 31),
                        idempotency_key=f"paper-history-session-{suffix}",
                        start_immediately=True,
                    ),
                    handler=session_handler,
                )
            )
        events = journal.list_events("paper-history-2")
        with pytest.raises(UnprocessableEntityError) as raised:
            asyncio.run(
                _original(get_paper_account_history)(
                    account_id="paper-history-2",
                    params=PaperHistoryQueryParams(
                        # Session 3 is bound to a different account: the
                        # cross-account replay must fail closed.
                        session_id="paper-history-session-3",
                        start_date=date(2026, 8, 31),
                        end_date=date(2026, 9, 1),
                        knowledge_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                        publication_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                        source_snapshot_ids=(_history_snapshot().snapshot_id,),
                        ledger_event_count=len(events),
                        ledger_hash=ledger_hash(events),
                    ),
                    query=history_query,
                )
            )
        assert raised.value.error_code == "PAPER_HISTORY_SESSION_ACCOUNT_MISMATCH"
    store.close()
    journal.close()


def test_paper_history_route_maps_missing_session_to_not_found(tmp_path: Path) -> None:
    database = str(tmp_path / "paper-history-missing-session.sqlite")
    journal = SqliteAccountEventJournal(database)
    store = SqlitePaperSessionStore(database)
    account_handler = CreatePaperAccountHandler(journal=journal, clock=lambda: NOW)
    history_query = GetPaperHistoryQuery(
        journal=journal,
        session_store=store,
        snapshot_reader=_SnapshotReader(),
        valuation_source=_EmptyBars(),
    )

    with patch("ditto_apps.api.routes.paper.asyncio.to_thread", side_effect=_inline):
        asyncio.run(
            _original(create_paper_account)(
                body=CreatePaperAccountBody(
                    account_id="paper-history-4",
                    name="无会话账户",
                    opened_at=NOW,
                    trade_date=date(2026, 8, 31),
                    initial_cash=Decimal("100"),
                    idempotency_key="paper-history-account-4",
                ),
                handler=account_handler,
            )
        )
        events = journal.list_events("paper-history-4")
        with pytest.raises(NotFoundError) as raised:
            asyncio.run(
                _original(get_paper_account_history)(
                    account_id="paper-history-4",
                    params=PaperHistoryQueryParams(
                        session_id="paper-history-session-never-created",
                        start_date=date(2026, 8, 31),
                        end_date=date(2026, 9, 1),
                        knowledge_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                        publication_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                        source_snapshot_ids=(_history_snapshot().snapshot_id,),
                        ledger_event_count=len(events),
                        ledger_hash=ledger_hash(events),
                    ),
                    query=history_query,
                )
            )
        assert "paper history query failed closed" in str(raised.value)
    store.close()
    journal.close()


def test_paper_history_query_params_coerce_plain_query_strings() -> None:
    """FastAPI hands query params as strings; the model must coerce them."""
    params = PaperHistoryQueryParams.model_validate(
        {
            "session_id": "paper-session-1",
            "start_date": "2026-08-31",
            "end_date": "2026-09-01",
            "knowledge_cutoff": "2026-09-01T12:00:00+08:00",
            "publication_cutoff": "2026-09-01T12:00:00+08:00",
            "source_snapshot_ids": ["snapshot:stock_daily:1"],
            "ledger_event_count": "2",
            "ledger_hash": "account-ledger:sha256:x",
        }
    )
    assert params.session_id == "paper-session-1"
    assert params.start_date == date(2026, 8, 31)
    assert params.ledger_event_count == 2
    assert params.source_snapshot_ids == ("snapshot:stock_daily:1",)


def test_paper_history_openapi_declares_the_series_contract() -> None:
    schema = create_openapi_app().openapi()
    schemas = schema["components"]["schemas"]
    assert "PaperHistoryResponse" in schemas
    properties = schemas["PaperHistoryResponse"]["properties"]
    assert "ledger_revision" in properties
    assert "points" in properties
    assert "segments" in properties
    operation = schema["paths"]["/api/v1/paper/accounts/{account_id}/history"]["get"]
    parameter_names = {parameter["name"] for parameter in operation["parameters"]}
    assert "session_id" in parameter_names
    assert "ledger_event_count" in parameter_names


def test_paper_catalog_routes_list_kind_filtered_accounts_and_sessions(
    tmp_path: Path,
) -> None:
    from ditto_application.queries.account_catalog import (
        ListPaperAccountsQuery,
        ListPaperSessionsQuery,
    )
    from ditto_apps.api.routes.paper import (
        list_paper_account_sessions,
        list_paper_accounts,
    )
    from ditto_portfolio.account_ledger import AccountDefinition, AccountKind

    database = str(tmp_path / "paper-catalog.sqlite")
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
    journal.create_account(
        AccountDefinition(
            account_id="manual-bystander",
            kind=AccountKind.MANUAL,
            name="实盘账户-不应出现在 PAPER 目录",
            opened_at=NOW,
        )
    )

    with patch("ditto_apps.api.routes.paper.asyncio.to_thread", side_effect=_inline):
        for account_id, name, opened in (
            ("paper-catalog-2", "模拟账户乙", date(2026, 8, 31)),
            ("paper-catalog-1", "模拟账户甲", date(2026, 8, 28)),
        ):
            asyncio.run(
                _original(create_paper_account)(
                    body=CreatePaperAccountBody(
                        account_id=account_id,
                        name=name,
                        opened_at=NOW,
                        trade_date=opened,
                        initial_cash=Decimal("100"),
                        idempotency_key=f"paper-catalog-{account_id}",
                    ),
                    handler=account_handler,
                )
            )
        for day, suffix in ((date(2026, 8, 31), "a"), (date(2026, 9, 1), "b")):
            asyncio.run(
                _original(create_paper_session)(
                    body=CreatePaperSessionBody(
                        session_id=f"paper-catalog-session-{suffix}",
                        account_id="paper-catalog-1",
                        strategy_id="strategy-catalog",
                        trade_date=day,
                        idempotency_key=f"paper-catalog-session-{suffix}",
                        start_immediately=True,
                    ),
                    handler=session_handler,
                )
            )
        accounts = asyncio.run(
            _original(list_paper_accounts)(
                query=ListPaperAccountsQuery(journal=journal),
            )
        )
        sessions = asyncio.run(
            _original(list_paper_account_sessions)(
                account_id="paper-catalog-1",
                query=ListPaperSessionsQuery(store=store),
            )
        )
        other_sessions = asyncio.run(
            _original(list_paper_account_sessions)(
                account_id="paper-catalog-2",
                query=ListPaperSessionsQuery(store=store),
            )
        )

    assert [entry.account_id for entry in accounts.data.accounts] == [
        "paper-catalog-1",
        "paper-catalog-2",
    ]
    first = accounts.data.accounts[0]
    assert first.account_kind == "paper"
    assert first.account_name == "模拟账户甲"
    assert first.currency == "CNY"
    assert [entry.session_id for entry in sessions.data.sessions] == [
        "paper-catalog-session-a",
        "paper-catalog-session-b",
    ]
    assert sessions.data.sessions[0].trade_date == "2026-08-31"
    assert sessions.data.sessions[0].status == "running"
    assert other_sessions.data.sessions == ()
    store.close()
    journal.close()
