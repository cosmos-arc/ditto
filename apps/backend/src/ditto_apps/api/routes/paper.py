"""Formal local PAPER account, session, execution, and recovery routes."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
    PausePaperSessionCommand,
    ReconcilePaperSessionCommand,
    StartPaperSessionCommand,
)
from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppNotFoundError,
    AppProcessError,
    AppQueryError,
)
from ditto_application.paper_contracts import (
    PaperFillAssumptionInput,
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperOrderCommand,
    OperatePaperSession,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.paper_session import GetPaperSessionQuery
from fastapi import APIRouter, Path, Query, status

from ditto_apps.api.errors import (
    ConflictError,
    NotFoundError,
    UnprocessableEntityError,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.paper import (
    CreatePaperAccountBody,
    CreatePaperSessionBody,
    OperatePaperOrderBody,
    PaperAccountLedgerResponse,
    PaperAccountReceiptResponse,
    PaperExecutionReceiptResponse,
    PaperReconciliationResponse,
    PaperRecoverResponse,
    PaperSessionCommandResponse,
    PaperSessionReadResponse,
    PaperSessionResponse,
    PausePaperSessionBody,
    ReconcilePaperSessionBody,
    RecoverPaperSessionBody,
)

router = APIRouter(prefix="/paper", tags=["paper"])


def _raise_error(exc: Exception) -> Never:
    if isinstance(exc, (AppNotFoundError,)) or (
        isinstance(exc, AppQueryError)
        and exc.details.get("code") == "PAPER_SESSION_NOT_FOUND"
    ):
        raise NotFoundError(str(exc)) from exc
    if isinstance(exc, AppConflictError):
        raise ConflictError(str(exc), error_code="PAPER_CONFLICT") from exc
    raise UnprocessableEntityError(
        str(exc),
        error_code="PAPER_INPUT_INVALID",
    ) from exc


@router.post(
    "/accounts",
    response_model=APIResponse[PaperAccountReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="paper_create_account",
)
@inject
async def create_paper_account(
    body: CreatePaperAccountBody,
    handler: Annotated[CreatePaperAccountHandler, FromComponent()],
) -> APIResponse[PaperAccountReceiptResponse]:
    """Create or replay a PAPER account with immutable opening cash."""
    try:
        receipt = await asyncio.to_thread(
            handler.handle,
            CreatePaperAccountCommand(
                account_id=body.account_id,
                name=body.name,
                opened_at=body.opened_at,
                trade_date=body.trade_date.isoformat(),
                initial_cash=body.initial_cash,
                idempotency_key=body.idempotency_key,
                currency=body.currency,
            ),
        )
    except (AppCommandError, ValueError) as exc:
        _raise_error(exc)
    return APIResponse(data=PaperAccountReceiptResponse.model_validate(receipt))


@router.get(
    "/accounts/{account_id}/ledger",
    response_model=APIResponse[PaperAccountLedgerResponse],
    operation_id="paper_get_account_ledger",
)
@inject
async def get_paper_account_ledger(
    account_id: Annotated[str, Path(min_length=1)],
    as_of: Annotated[date, Query()],
    query: Annotated[AccountLedgerQuery, FromComponent()],
) -> APIResponse[PaperAccountLedgerResponse]:
    """Rebuild one exact PAPER account ledger at the requested date."""
    try:
        result = await asyncio.to_thread(
            query.get_paper,
            account_id=account_id,
            as_of=as_of.isoformat(),
        )
    except AppQueryError as exc:
        _raise_error(exc)
    return APIResponse(data=PaperAccountLedgerResponse.model_validate(result))


@router.post(
    "/sessions",
    response_model=APIResponse[PaperSessionCommandResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="paper_create_session",
)
@inject
async def create_paper_session(
    body: CreatePaperSessionBody,
    handler: Annotated[PaperSessionCommandHandler, FromComponent()],
) -> APIResponse[PaperSessionCommandResponse]:
    """Create and optionally start one formal paper session."""
    try:
        receipt = await asyncio.to_thread(
            handler.create,
            CreatePaperSessionCommand(
                session_id=body.session_id,
                account_id=body.account_id,
                strategy_id=body.strategy_id,
                trade_date=body.trade_date.isoformat(),
                idempotency_key=body.idempotency_key,
            ),
        )
        if body.start_immediately:
            receipt = await asyncio.to_thread(
                handler.start,
                StartPaperSessionCommand(
                    session_id=body.session_id,
                    idempotency_key=f"{body.idempotency_key}:start",
                ),
            )
    except (AppCommandError, ValueError) as exc:
        _raise_error(exc)
    return APIResponse(data=PaperSessionCommandResponse.model_validate(receipt))


@router.get(
    "/sessions/{session_id}",
    response_model=APIResponse[PaperSessionReadResponse],
    operation_id="paper_get_session",
)
@inject
async def get_paper_session(
    session_id: Annotated[str, Path(min_length=1)],
    query: Annotated[GetPaperSessionQuery, FromComponent()],
) -> APIResponse[PaperSessionReadResponse]:
    """Read exact session, execution, fill, lineage, and EOD evidence."""
    try:
        result = await asyncio.to_thread(query.get, session_id)
    except AppQueryError as exc:
        _raise_error(exc)
    executions = tuple(
        PaperExecutionReceiptResponse.from_info(status="replayed", info=execution)
        for execution in result.executions
    )
    return APIResponse(
        data=PaperSessionReadResponse(
            session=PaperSessionResponse.model_validate(result.session),
            executions=executions,
            latest_reconciliation=(
                PaperReconciliationResponse.model_validate(result.latest_reconciliation)
                if result.latest_reconciliation is not None
                else None
            ),
        )
    )


@router.post(
    "/sessions/{session_id}/orders",
    response_model=APIResponse[PaperExecutionReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="paper_operate_order",
)
@inject
async def operate_paper_order(
    body: OperatePaperOrderBody,
    process: Annotated[OperatePaperSession, FromComponent()],
    session_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[PaperExecutionReceiptResponse]:
    """Execute or replay one complete deterministic paper-order input."""
    try:
        command = _operate_command(session_id, body)
        receipt = await asyncio.to_thread(process.execute, command)
    except (AppCommandError, AppProcessError, ValueError) as exc:
        _raise_error(exc)
    return APIResponse(
        data=PaperExecutionReceiptResponse.from_info(
            status="replayed" if receipt.status == "replayed" else "created",
            info=receipt.execution,
        )
    )


@router.post(
    "/sessions/{session_id}/pause",
    response_model=APIResponse[PaperSessionCommandResponse],
    operation_id="paper_pause_session",
)
@inject
async def pause_paper_session(
    body: PausePaperSessionBody,
    handler: Annotated[PaperSessionCommandHandler, FromComponent()],
    session_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[PaperSessionCommandResponse]:
    """Pause or replay one formal paper session transition."""
    try:
        receipt = await asyncio.to_thread(
            handler.pause,
            PausePaperSessionCommand(
                session_id=session_id,
                idempotency_key=body.idempotency_key,
                reason=body.reason,
            ),
        )
    except AppCommandError as exc:
        _raise_error(exc)
    return APIResponse(data=PaperSessionCommandResponse.model_validate(receipt))


@router.post(
    "/sessions/{session_id}/reconcile",
    response_model=APIResponse[PaperReconciliationResponse],
    operation_id="paper_reconcile_session",
)
@inject
async def reconcile_paper_session(
    body: ReconcilePaperSessionBody,
    handler: Annotated[PaperSessionCommandHandler, FromComponent()],
    session_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[PaperReconciliationResponse]:
    """Create or replay a fill-to-ledger EOD checksum."""
    try:
        receipt = await asyncio.to_thread(
            handler.reconcile,
            ReconcilePaperSessionCommand(
                session_id=session_id,
                idempotency_key=body.idempotency_key,
            ),
        )
    except AppCommandError as exc:
        _raise_error(exc)
    return APIResponse(data=PaperReconciliationResponse.model_validate(receipt))


@router.post(
    "/sessions/{session_id}/recover",
    response_model=APIResponse[PaperRecoverResponse],
    operation_id="paper_recover_session",
)
@inject
async def recover_paper_session(
    body: RecoverPaperSessionBody,
    process: Annotated[OperatePaperSession, FromComponent()],
    session_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[PaperRecoverResponse]:
    """Repair ledger markers after an interrupted paper operation."""
    try:
        recovered = await asyncio.to_thread(process.recover, session_id)
    except (AppCommandError, AppProcessError) as exc:
        _raise_error(exc)
    return APIResponse(
        data=PaperRecoverResponse(
            idempotency_key=body.idempotency_key,
            recovered_execution_count=len(recovered),
        )
    )


def _operate_command(
    session_id: str,
    body: OperatePaperOrderBody,
) -> OperatePaperOrderCommand:
    return OperatePaperOrderCommand(
        session_id=session_id,
        idempotency_key=body.idempotency_key,
        order_id=body.order_id,
        instrument_id=body.instrument_id,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        price=body.price,
        trade_date=body.trade_date.isoformat(),
        decision_at=body.decision_at,
        execution_at=body.execution_at,
        settlement_date=body.settlement_date.isoformat(),
        position_quantity=body.position_quantity,
        available_quantity=body.available_quantity,
        market=PaperMarketSnapshotInput(
            dataset_id=body.market.dataset_id,
            source=body.market.source,
            source_snapshot_id=body.market.source_snapshot_id,
            observed_at=body.market.observed_at,
            publication_cutoff=body.market.publication_cutoff,
            open=body.market.open,
            high=body.market.high,
            low=body.market.low,
            close=body.market.close,
            prev_close=body.market.prev_close,
            volume=body.market.volume,
            amount=body.market.amount,
            is_suspended=body.market.is_suspended,
            limit_up=body.market.limit_up,
            limit_down=body.market.limit_down,
            avg_volume_20d=body.market.avg_volume_20d,
        ),
        rules=PaperInstrumentRulesInput(
            asset_class=body.rules.asset_class,
            exchange=body.rules.exchange,
            currency=body.rules.currency,
            tick_size=body.rules.tick_size,
            lot_size=body.rules.lot_size,
            multiplier=body.rules.multiplier,
            board_segment=body.rules.board_segment,
            lifecycle_state=body.rules.lifecycle_state,
            settlement_cycle=body.rules.settlement_cycle,
            price_limit_pct=body.rules.price_limit_pct,
            commission_rate=body.rules.commission_rate,
            min_commission=body.rules.min_commission,
            stamp_duty_rate=body.rules.stamp_duty_rate,
            transfer_fee_rate=body.rules.transfer_fee_rate,
        ),
        assumption=PaperFillAssumptionInput(
            assumption_id=body.assumption.assumption_id,
            version=body.assumption.version,
            reference_price_field=body.assumption.reference_price_field,
            slippage_bps=body.assumption.slippage_bps,
        ),
    )
