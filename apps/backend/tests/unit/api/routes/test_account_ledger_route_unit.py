"""MANUAL account-ledger route and OpenAPI contract tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import pytest
from ditto_application.commands.account_ledger import (
    CreateAccountHandler,
    ManualAccountCommandHandler,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.portfolio_history import GetManualHistoryQuery
from ditto_apps.api.errors import NotFoundError
from ditto_apps.api.routes.account_ledger import (
    correct_manual_event,
    create_manual_account,
    get_manual_account_history,
    get_manual_account_ledger,
    record_manual_event,
    reverse_manual_event,
)
from ditto_apps.models.account_ledger import (
    CorrectManualEventBody,
    CreateManualAccountBody,
    ManualEventBody,
    ManualHistoryQueryParams,
    ReverseManualEventBody,
)
from ditto_apps.openapi_contract import create_openapi_app
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from pydantic import ValidationError

NOW = datetime(2026, 8, 31, 9, 30, tzinfo=UTC)


async def _inline(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


def _original[T](
    function: Callable[..., Awaitable[T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    return cast(
        Callable[..., Coroutine[Any, Any, T]],
        function.__dict__["__dishka_orig_func__"],
    )


def _opening_body(*, idempotency_key: str = "opening") -> ManualEventBody:
    return ManualEventBody(
        event_type="opening_cash",
        trade_date=date(2026, 8, 31),
        settlement_date=date(2026, 8, 31),
        idempotency_key=idempotency_key,
        actor="user:chevy",
        gross_amount=Decimal("100000"),
    )


def test_manual_routes_create_append_correct_reverse_and_rebuild(tmp_path) -> None:
    journal = SqliteAccountEventJournal(str(tmp_path / "account.sqlite"))
    create_handler = CreateAccountHandler(journal=journal)
    manual_handler = ManualAccountCommandHandler(journal=journal, clock=lambda: NOW)
    query = AccountLedgerQuery(journal=journal)

    with patch(
        "ditto_apps.api.routes.account_ledger.asyncio.to_thread",
        side_effect=_inline,
    ):
        created = asyncio.run(
            _original(create_manual_account)(
                body=CreateManualAccountBody(
                    account_id="manual-main",
                    name="我的账户",
                    opened_at=NOW,
                ),
                handler=create_handler,
            )
        )
        opening = asyncio.run(
            _original(record_manual_event)(
                account_id="manual-main",
                body=_opening_body(),
                handler=manual_handler,
            )
        )
        replayed = asyncio.run(
            _original(record_manual_event)(
                account_id="manual-main",
                body=_opening_body(),
                handler=manual_handler,
            )
        )
        buy = asyncio.run(
            _original(record_manual_event)(
                account_id="manual-main",
                body=ManualEventBody(
                    event_type="buy",
                    trade_date=date(2026, 8, 31),
                    settlement_date=date(2026, 9, 1),
                    idempotency_key="buy",
                    actor="user:chevy",
                    instrument_id=InstrumentId(600519),
                    quantity=Decimal("100"),
                    price=Decimal("100"),
                    fees=Decimal("5"),
                ),
                handler=manual_handler,
            )
        )
        buy_event = buy.data.event
        assert buy_event is not None
        correction = asyncio.run(
            _original(correct_manual_event)(
                account_id="manual-main",
                body=CorrectManualEventBody(
                    corrects_event_id=buy_event.event_id,
                    replacement=ManualEventBody(
                        event_type="buy",
                        trade_date=date(2026, 8, 31),
                        settlement_date=date(2026, 9, 1),
                        idempotency_key="correct-buy",
                        actor="user:chevy",
                        instrument_id=InstrumentId(600519),
                        quantity=Decimal("100"),
                        price=Decimal("90"),
                        fees=Decimal("5"),
                    ),
                ),
                handler=manual_handler,
            )
        )
        correction_event = correction.data.event
        assert correction_event is not None
        reversal = asyncio.run(
            _original(reverse_manual_event)(
                account_id="manual-main",
                body=ReverseManualEventBody(
                    reverses_event_id=correction_event.event_id,
                    trade_date=date(2026, 8, 31),
                    settlement_date=date(2026, 8, 31),
                    idempotency_key="reverse-correction",
                    actor="user:chevy",
                ),
                handler=manual_handler,
            )
        )
        reversal_event = reversal.data.event
        assert reversal_event is not None
        ledger = asyncio.run(
            _original(get_manual_account_ledger)(
                account_id="manual-main",
                as_of=date(2026, 8, 31),
                query=query,
            )
        )

    assert created.data.account.kind == "manual"
    assert created.data.event is None
    assert opening.data.status == "created"
    assert replayed.data.status == "replayed"
    assert correction_event.corrects_event_id == buy_event.event_id
    assert reversal_event.reverses_event_id == correction_event.event_id
    assert ledger.data.account.kind == "manual"
    assert ledger.data.snapshot.cash.available == Decimal("89995.00")
    assert ledger.data.snapshot.cash.settled == Decimal("100000.00")
    assert ledger.data.snapshot.positions[0].available_quantity == Decimal("0")
    assert len(ledger.data.events) == 4
    journal.close()


def test_manual_query_maps_unknown_account_to_not_found(tmp_path) -> None:
    journal = SqliteAccountEventJournal(str(tmp_path / "account.sqlite"))

    with (
        patch(
            "ditto_apps.api.routes.account_ledger.asyncio.to_thread",
            side_effect=_inline,
        ),
        pytest.raises(NotFoundError, match="account not found"),
    ):
        asyncio.run(
            _original(get_manual_account_ledger)(
                account_id="missing",
                as_of=date(2026, 8, 31),
                query=AccountLedgerQuery(journal=journal),
            )
        )
    journal.close()


def test_manual_request_models_are_strict_and_exclude_control_events() -> None:
    with pytest.raises(ValidationError):
        ManualEventBody.model_validate(
            {
                "event_type": "correction",
                "trade_date": date(2026, 8, 31),
                "settlement_date": date(2026, 8, 31),
                "idempotency_key": "bad",
                "actor": "user:chevy",
            }
        )
    with pytest.raises(ValidationError):
        CreateManualAccountBody.model_validate(
            {
                "account_id": "manual-main",
                "name": "我的账户",
                "opened_at": NOW,
                "unexpected": True,
            }
        )


def test_manual_request_models_accept_canonical_json_scalars() -> None:
    """HTTP JSON strings and arrays must survive the strict request boundary."""
    account = CreateManualAccountBody.model_validate(
        {
            "account_id": "manual-main",
            "name": "我的账户",
            "opened_at": "2026-08-31T09:30:00+08:00",
        }
    )
    event = ManualEventBody.model_validate(
        {
            "event_type": "opening_cash",
            "trade_date": "2026-08-31",
            "settlement_date": "2026-08-31",
            "idempotency_key": "opening",
            "actor": "user:chevy",
            "gross_amount": "100000.00",
            "net_cash": "100000.00",
            "attachment_refs": ["receipt:1"],
        }
    )

    assert account.opened_at == datetime.fromisoformat("2026-08-31T09:30:00+08:00")
    assert event.trade_date == date(2026, 8, 31)
    assert event.gross_amount == Decimal("100000.00")
    assert event.attachment_refs == ("receipt:1",)


def test_manual_openapi_surface_has_stable_operation_ids() -> None:
    schema = create_openapi_app().openapi()

    expected = {
        ("/api/v1/manual/accounts", "post"): "manual_create_account",
        ("/api/v1/manual/accounts", "get"): "manual_list_accounts",
        (
            "/api/v1/manual/accounts/{account_id}/events",
            "post",
        ): "manual_record_event",
        (
            "/api/v1/manual/accounts/{account_id}/corrections",
            "post",
        ): "manual_correct_event",
        (
            "/api/v1/manual/accounts/{account_id}/reversals",
            "post",
        ): "manual_reverse_event",
        (
            "/api/v1/manual/accounts/{account_id}/ledger",
            "get",
        ): "manual_get_ledger",
        (
            "/api/v1/manual/accounts/{account_id}/history",
            "get",
        ): "manual_get_history",
    }
    for (path, method), operation_id in expected.items():
        assert schema["paths"][path][method]["operationId"] == operation_id


def test_manual_catalog_route_lists_only_manual_accounts(tmp_path) -> None:
    from ditto_application.queries.account_catalog import ListManualAccountsQuery
    from ditto_apps.api.routes.account_ledger import list_manual_accounts
    from ditto_portfolio.account_ledger import AccountDefinition, AccountKind

    journal = SqliteAccountEventJournal(str(tmp_path / "manual-catalog.sqlite"))
    journal.create_account(
        AccountDefinition(
            account_id="manual-catalog-2",
            kind=AccountKind.MANUAL,
            name="实盘账户乙",
            opened_at=NOW,
        )
    )
    journal.create_account(
        AccountDefinition(
            account_id="manual-catalog-1",
            kind=AccountKind.MANUAL,
            name="实盘账户甲",
            opened_at=NOW,
        )
    )
    journal.create_account(
        AccountDefinition(
            account_id="paper-bystander",
            kind=AccountKind.PAPER,
            name="模拟账户-不应出现在 MANUAL 目录",
            opened_at=NOW,
        )
    )

    with patch(
        "ditto_apps.api.routes.account_ledger.asyncio.to_thread",
        side_effect=_inline,
    ):
        result = asyncio.run(
            _original(list_manual_accounts)(
                query=ListManualAccountsQuery(journal=journal),
            )
        )

    assert [entry.account_id for entry in result.data.accounts] == [
        "manual-catalog-1",
        "manual-catalog-2",
    ]
    first = result.data.accounts[0]
    assert first.account_kind == "manual"
    assert first.account_name == "实盘账户甲"
    assert first.currency == "CNY"
    journal.close()


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


def _history_query(journal: SqliteAccountEventJournal) -> GetManualHistoryQuery:
    return GetManualHistoryQuery(
        journal=journal,
        snapshot_reader=_SnapshotReader(),
        valuation_source=_EmptyBars(),
    )


def _history_snapshot() -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="route-fixture",
            request_start="2026-08-31",
            request_end="2026-09-01",
            schema_version="market.stock_daily.v1",
            checksum="sha256:route-bars",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="sha256:params",
            response_metadata=(("rows", "0"),),
            license_record_id="license:fixture",
            row_count=0,
            payload_uri="file:///tmp/route-bars.parquet",
            payload_retained=True,
            created_at=NOW,
        )
    )


def test_manual_history_route_replays_cash_flow_adjusted_series(tmp_path) -> None:
    journal = SqliteAccountEventJournal(str(tmp_path / "account.sqlite"))
    create_handler = CreateAccountHandler(journal=journal)
    manual_handler = ManualAccountCommandHandler(journal=journal, clock=lambda: NOW)
    history_query = _history_query(journal)

    with patch(
        "ditto_apps.api.routes.account_ledger.asyncio.to_thread",
        side_effect=_inline,
    ):
        asyncio.run(
            _original(create_manual_account)(
                body=CreateManualAccountBody(
                    account_id="manual-history",
                    name="历史账户",
                    opened_at=NOW,
                ),
                handler=create_handler,
            )
        )
        asyncio.run(
            _original(record_manual_event)(
                account_id="manual-history",
                body=ManualEventBody(
                    event_type="opening_cash",
                    trade_date=date(2026, 8, 31),
                    settlement_date=date(2026, 8, 31),
                    idempotency_key="opening",
                    actor="user:chevy",
                    gross_amount=Decimal("100"),
                ),
                handler=manual_handler,
            )
        )
        asyncio.run(
            _original(record_manual_event)(
                account_id="manual-history",
                body=ManualEventBody(
                    event_type="deposit",
                    trade_date=date(2026, 9, 1),
                    settlement_date=date(2026, 9, 1),
                    idempotency_key="deposit",
                    actor="user:chevy",
                    gross_amount=Decimal("100"),
                    flow_position="start_of_day",
                ),
                handler=manual_handler,
            )
        )
        ledger = asyncio.run(
            _original(get_manual_account_ledger)(
                account_id="manual-history",
                as_of=date(2026, 9, 1),
                query=AccountLedgerQuery(journal=journal),
            )
        )
        result = asyncio.run(
            _original(get_manual_account_history)(
                account_id="manual-history",
                params=ManualHistoryQueryParams(
                    start_date=date(2026, 8, 31),
                    end_date=date(2026, 9, 1),
                    knowledge_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                    publication_cutoff=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                    source_snapshot_ids=(_history_snapshot().snapshot_id,),
                    ledger_event_count=ledger.data.ledger_revision.event_count,
                    ledger_hash=ledger.data.ledger_revision.ledger_hash,
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
    assert result.data.segments[0].linked_return == Decimal("0")
    assert result.data.method == "twr-linked-v1"
    assert result.data.currency == "CNY"
    assert result.data.result_id.startswith("manual-history:sha256:")
    journal.close()


def test_manual_history_query_params_coerce_plain_query_strings() -> None:
    """FastAPI hands query params as strings; the model must coerce them."""
    params = ManualHistoryQueryParams.model_validate(
        {
            "start_date": "2026-08-31",
            "end_date": "2026-09-01",
            "knowledge_cutoff": "2026-09-01T12:00:00+08:00",
            "publication_cutoff": "2026-09-01T12:00:00+08:00",
            "source_snapshot_ids": ["snapshot:stock_daily:1"],
            "ledger_event_count": "2",
            "ledger_hash": "account-ledger:sha256:x",
        }
    )
    assert params.start_date == date(2026, 8, 31)
    assert params.end_date == date(2026, 9, 1)
    assert params.ledger_event_count == 2
    assert params.source_snapshot_ids == ("snapshot:stock_daily:1",)


def test_manual_history_openapi_declares_flow_position_and_revision() -> None:
    schema = create_openapi_app().openapi()
    schemas = schema["components"]["schemas"]
    assert "flow_position" in schemas["ManualEventBody"]["properties"]
    assert "ledger_revision" in schemas["AccountLedgerResponse"]["properties"]
    assert "ManualHistoryResponse" in schemas
