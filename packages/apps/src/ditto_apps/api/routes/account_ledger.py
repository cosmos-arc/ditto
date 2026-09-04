"""Immutable MANUAL account journal HTTP routes."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.account_ledger import (
    CorrectManualEventCommand,
    CreateAccountCommand,
    CreateAccountHandler,
    ManualAccountCommandHandler,
    ManualEventInput,
    RecordManualEventCommand,
    ReverseManualEventCommand,
)
from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppNotFoundError,
    AppQueryError,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from fastapi import APIRouter, Path, Query, status

from ditto_apps.api.errors import (
    ConflictError,
    NotFoundError,
    UnprocessableEntityError,
)
from ditto_apps.models.account_ledger import (
    AccountCommandReceiptResponse,
    AccountLedgerResponse,
    CorrectManualEventBody,
    CreateManualAccountBody,
    ManualEventBody,
    ReverseManualEventBody,
)
from ditto_apps.models.common import APIResponse

router = APIRouter(prefix="/manual/accounts", tags=["manual"])


def _raise_command_error(exc: AppCommandError) -> Never:
    if isinstance(exc, AppNotFoundError):
        raise NotFoundError(str(exc)) from exc
    if isinstance(exc, AppConflictError):
        raise ConflictError(str(exc), error_code="ACCOUNT_LEDGER_CONFLICT") from exc
    raise UnprocessableEntityError(
        str(exc),
        error_code="ACCOUNT_LEDGER_COMMAND_INVALID",
    ) from exc


def _raise_query_error(exc: AppQueryError) -> Never:
    code = str(exc.details.get("code", "ACCOUNT_LEDGER_QUERY_INVALID"))
    if code == "ACCOUNT_NOT_FOUND":
        raise NotFoundError(str(exc)) from exc
    raise UnprocessableEntityError(str(exc), error_code=code) from exc


def _event_input(body: ManualEventBody) -> ManualEventInput:
    return ManualEventInput(
        event_type=ManualEventInput.parse_business_event_type(body.event_type),
        trade_date=body.trade_date.isoformat(),
        settlement_date=body.settlement_date.isoformat(),
        idempotency_key=body.idempotency_key,
        actor=body.actor,
        instrument_id=body.instrument_id,
        quantity=body.quantity,
        price=body.price,
        gross_amount=body.gross_amount,
        fees=body.fees,
        tax=body.tax,
        net_cash=body.net_cash,
        note=body.note,
        attachment_refs=body.attachment_refs,
        external_reference=body.external_reference,
    )


@router.post(
    "",
    response_model=APIResponse[AccountCommandReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="manual_create_account",
)
@inject
async def create_manual_account(
    body: CreateManualAccountBody,
    handler: Annotated[CreateAccountHandler, FromComponent()],
) -> APIResponse[AccountCommandReceiptResponse]:
    """Create or exactly replay one permanently MANUAL account identity."""
    try:
        receipt = await asyncio.to_thread(
            handler.handle,
            CreateAccountCommand.manual(
                account_id=body.account_id,
                name=body.name,
                opened_at=body.opened_at,
                currency=body.currency,
            ),
        )
    except AppCommandError as exc:
        _raise_command_error(exc)
    return APIResponse(data=AccountCommandReceiptResponse.model_validate(receipt))


@router.post(
    "/{account_id}/events",
    response_model=APIResponse[AccountCommandReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="manual_record_event",
)
@inject
async def record_manual_event(
    body: ManualEventBody,
    handler: Annotated[ManualAccountCommandHandler, FromComponent()],
    account_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[AccountCommandReceiptResponse]:
    """Append one immutable MANUAL account business event."""
    try:
        receipt = await asyncio.to_thread(
            handler.record,
            RecordManualEventCommand(account_id=account_id, event=_event_input(body)),
        )
    except AppCommandError as exc:
        _raise_command_error(exc)
    return APIResponse(data=AccountCommandReceiptResponse.model_validate(receipt))


@router.post(
    "/{account_id}/corrections",
    response_model=APIResponse[AccountCommandReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="manual_correct_event",
)
@inject
async def correct_manual_event(
    body: CorrectManualEventBody,
    handler: Annotated[ManualAccountCommandHandler, FromComponent()],
    account_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[AccountCommandReceiptResponse]:
    """Append a correction while retaining the original event."""
    try:
        receipt = await asyncio.to_thread(
            handler.correct,
            CorrectManualEventCommand(
                account_id=account_id,
                corrects_event_id=body.corrects_event_id,
                replacement=_event_input(body.replacement),
            ),
        )
    except AppCommandError as exc:
        _raise_command_error(exc)
    return APIResponse(data=AccountCommandReceiptResponse.model_validate(receipt))


@router.post(
    "/{account_id}/reversals",
    response_model=APIResponse[AccountCommandReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="manual_reverse_event",
)
@inject
async def reverse_manual_event(
    body: ReverseManualEventBody,
    handler: Annotated[ManualAccountCommandHandler, FromComponent()],
    account_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[AccountCommandReceiptResponse]:
    """Append a reversal while retaining the referenced event."""
    try:
        receipt = await asyncio.to_thread(
            handler.reverse,
            ReverseManualEventCommand(
                account_id=account_id,
                reverses_event_id=body.reverses_event_id,
                trade_date=body.trade_date.isoformat(),
                settlement_date=body.settlement_date.isoformat(),
                idempotency_key=body.idempotency_key,
                actor=body.actor,
                note=body.note,
            ),
        )
    except AppCommandError as exc:
        _raise_command_error(exc)
    return APIResponse(data=AccountCommandReceiptResponse.model_validate(receipt))


@router.get(
    "/{account_id}/ledger",
    response_model=APIResponse[AccountLedgerResponse],
    operation_id="manual_get_ledger",
)
@inject
async def get_manual_account_ledger(
    query: Annotated[AccountLedgerQuery, FromComponent()],
    account_id: Annotated[str, Path(min_length=1)],
    as_of: Annotated[date, Query()],
) -> APIResponse[AccountLedgerResponse]:
    """Rebuild one exact MANUAL account view at an explicit as-of date."""
    try:
        result = await asyncio.to_thread(
            query.get_manual,
            account_id=account_id,
            as_of=as_of.isoformat(),
        )
    except AppQueryError as exc:
        _raise_query_error(exc)
    return APIResponse(data=AccountLedgerResponse.model_validate(result))
