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
from ditto_apps.api.errors import NotFoundError
from ditto_apps.api.routes.account_ledger import (
    correct_manual_event,
    create_manual_account,
    get_manual_account_ledger,
    record_manual_event,
    reverse_manual_event,
)
from ditto_apps.models.account_ledger import (
    CorrectManualEventBody,
    CreateManualAccountBody,
    ManualEventBody,
    ReverseManualEventBody,
)
from ditto_apps.openapi_contract import create_openapi_app
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
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
        "/api/v1/manual/accounts": "manual_create_account",
        "/api/v1/manual/accounts/{account_id}/events": "manual_record_event",
        "/api/v1/manual/accounts/{account_id}/corrections": ("manual_correct_event"),
        "/api/v1/manual/accounts/{account_id}/reversals": "manual_reverse_event",
        "/api/v1/manual/accounts/{account_id}/ledger": "manual_get_ledger",
    }
    for path, operation_id in expected.items():
        method = "get" if path.endswith("/ledger") else "post"
        assert schema["paths"][path][method]["operationId"] == operation_id
