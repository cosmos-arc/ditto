"""Crash-safe orchestration for one formal paper-session order."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256

import orjson
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperOrder,
    PaperRealityContext,
)
from ditto_execution.paper.reality import ASharePaperReality
from ditto_execution.paper.session import (
    PaperExecutionRecord,
    PaperSessionConflictError,
    PaperSessionStatus,
    PaperSessionStorePort,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    MarketSnapshot,
    TradingRuleSet,
)
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventJournalPort,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    AccountLedgerError,
    create_account_event,
)

from ditto_application.exceptions import (
    AppConflictError,
    AppNotFoundError,
    AppProcessError,
)
from ditto_application.paper_contracts import (
    PaperExecutionInfo,
    PaperFillAssumptionInput,
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
    to_paper_execution_info,
)

__all__ = [
    "OperatePaperOrderCommand",
    "OperatePaperReceipt",
    "OperatePaperSession",
]


@dataclass(frozen=True, kw_only=True)
class OperatePaperOrderCommand:
    """Complete deterministic inputs for one paper execution attempt."""

    session_id: str
    idempotency_key: str
    order_id: str
    instrument_id: int
    side: str
    order_type: str
    quantity: int
    price: float | None
    trade_date: str
    market: PaperMarketSnapshotInput
    rules: PaperInstrumentRulesInput
    assumption: PaperFillAssumptionInput
    decision_at: datetime
    execution_at: datetime
    settlement_date: str
    position_quantity: int
    available_quantity: int


@dataclass(frozen=True, kw_only=True)
class OperatePaperReceipt:
    """Created or replayed durable execution receipt."""

    status: str
    execution: PaperExecutionInfo


@dataclass(frozen=True, kw_only=True)
class _ResolvedPaperInputs:
    order: Order
    lineage: MarketSnapshotLineage
    rules: InstrumentRules
    assumption: FillAssumption


class OperatePaperSession:
    """Persist outcome first, then idempotently close the PAPER ledger gap."""

    def __init__(
        self,
        *,
        store: PaperSessionStorePort,
        account_journal: AccountEventJournalPort,
        reality: ASharePaperReality | None = None,
        after_execution_persisted: Callable[[], None] | None = None,
    ) -> None:
        self._store = store
        self._account_journal = account_journal
        self._reality = reality or ASharePaperReality()
        self._after_execution_persisted = after_execution_persisted

    def execute(self, command: OperatePaperOrderCommand) -> OperatePaperReceipt:
        """Execute once or recover the exact persisted execution."""
        resolved = _resolve_inputs(command)
        session = self._store.get_session(command.session_id)
        if session is None:
            raise AppNotFoundError(f"paper session not found: {command.session_id}")
        if session.status is not PaperSessionStatus.RUNNING:
            raise AppConflictError("paper session must be running to execute orders")
        if resolved.order.trade_date != session.trade_date:
            raise AppProcessError(
                "paper order trade_date does not match session",
                code="PAPER_TRADE_DATE_MISMATCH",
            )
        request_hash = _request_hash(command)
        existing = self._store.get_execution(
            command.session_id,
            command.idempotency_key,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise AppConflictError("paper execution idempotency payload conflict")
            return OperatePaperReceipt(
                status="replayed",
                execution=to_paper_execution_info(self._ensure_ledger(existing)),
            )

        account = self._account_journal.get_account(session.account_id)
        if account is None:
            raise AppNotFoundError(f"paper account not found: {session.account_id}")
        if account.kind is not AccountKind.PAPER:
            raise AppConflictError("paper session account is not a PAPER account")
        paper_order = _paper_order(
            command,
            order=resolved.order,
            account_id=session.account_id,
        )
        result = self._reality.execute(
            paper_order=paper_order,
            lineage=resolved.lineage,
            rules=resolved.rules,
            assumption=resolved.assumption,
            context=PaperRealityContext(
                decision_at=command.decision_at,
                execution_at=command.execution_at,
                settlement_date=command.settlement_date,
                position_quantity=command.position_quantity,
                available_quantity=command.available_quantity,
            ),
        )
        execution = PaperExecutionRecord(
            execution_id=_execution_id(command.session_id, command.idempotency_key),
            session_id=command.session_id,
            account_id=session.account_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            result=result,
            assumption=resolved.assumption,
            lineage=resolved.lineage,
            created_at=command.decision_at,
        )
        try:
            persisted = self._store.append_execution(execution)
        except PaperSessionConflictError as exc:
            raise AppConflictError(str(exc)) from exc
        if self._after_execution_persisted is not None:
            self._after_execution_persisted()
        return OperatePaperReceipt(
            status="created",
            execution=to_paper_execution_info(self._ensure_ledger(persisted)),
        )

    def recover(self, session_id: str) -> tuple[PaperExecutionInfo, ...]:
        """Repair every persisted fill missing its corresponding ledger event."""
        session = self._store.get_session(session_id)
        if session is None:
            raise AppNotFoundError(f"paper session not found: {session_id}")
        return tuple(
            to_paper_execution_info(self._ensure_ledger(record))
            for record in self._store.list_executions(session_id)
        )

    def _ensure_ledger(self, record: PaperExecutionRecord) -> PaperExecutionRecord:
        fill = record.result.fill
        if fill is None:
            return record
        if record.ledger_event_id is not None:
            return record
        account = self._account_journal.get_account(record.account_id)
        if account is None:
            raise AppNotFoundError(f"paper account not found: {record.account_id}")
        idempotency_key = f"paper-ledger:{record.execution_id}"
        existing = self._account_journal.find_by_idempotency_key(
            record.account_id,
            idempotency_key,
        )
        event = _account_event(
            record=record,
            account=account,
            event_id=(
                existing.event_id
                if existing is not None
                else _ledger_event_id(record.execution_id)
            ),
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.event_hash != event.event_hash:
                raise AppConflictError("paper ledger idempotency payload conflict")
            event = existing
        else:
            try:
                event = self._account_journal.append(event)
            except (AccountLedgerError, PaperSessionConflictError) as exc:
                raise AppProcessError(
                    "paper ledger append failed",
                    code="PAPER_LEDGER_APPEND_FAILED",
                ) from exc
        try:
            return self._store.mark_execution_ledgered(
                record.execution_id,
                event.event_id,
            )
        except PaperSessionConflictError as exc:
            raise AppConflictError(str(exc)) from exc


def _paper_order(
    command: OperatePaperOrderCommand,
    *,
    order: Order,
    account_id: str,
) -> PaperOrder:
    return PaperOrder.create(
        session_id=command.session_id,
        account_id=account_id,
        idempotency_key=command.idempotency_key,
        order=order,
        submitted_at=command.decision_at,
    ).submit()


def _request_hash(command: OperatePaperOrderCommand) -> str:
    resolved = _resolve_inputs(command)
    payload = {
        "session_id": command.session_id,
        "idempotency_key": command.idempotency_key,
        "order": resolved.order,
        "market_lineage_hash": resolved.lineage.lineage_hash,
        "assumption_hash": resolved.assumption.assumption_hash,
        "rules": resolved.rules,
        "decision_at": command.decision_at.isoformat(),
        "execution_at": command.execution_at.isoformat(),
        "settlement_date": command.settlement_date,
        "position_quantity": command.position_quantity,
        "available_quantity": command.available_quantity,
    }
    encoded = orjson.dumps(
        payload,
        option=orjson.OPT_SERIALIZE_DATACLASS | orjson.OPT_SORT_KEYS,
    )
    return f"paper-request:sha256:{sha256(encoded).hexdigest()}"


def _resolve_inputs(command: OperatePaperOrderCommand) -> _ResolvedPaperInputs:
    iid = InstrumentId(command.instrument_id)
    snapshot = MarketSnapshot(
        trade_date=command.trade_date,
        instrument_id=iid,
        open=command.market.open,
        high=command.market.high,
        low=command.market.low,
        close=command.market.close,
        prev_close=command.market.prev_close,
        volume=command.market.volume,
        amount=command.market.amount,
        is_suspended=command.market.is_suspended,
        limit_up=command.market.limit_up,
        limit_down=command.market.limit_down,
        avg_volume_20d=command.market.avg_volume_20d,
    )
    lineage = MarketSnapshotLineage.create(
        snapshot=snapshot,
        dataset_id=command.market.dataset_id,
        source=command.market.source,
        source_snapshot_id=command.market.source_snapshot_id,
        observed_at=command.market.observed_at,
        publication_cutoff=command.market.publication_cutoff,
    )
    rules: InstrumentRules = (
        InstrumentDefinition(
            instrument_id=iid,
            asset_class=command.rules.asset_class,
            exchange=command.rules.exchange,
            currency=command.rules.currency,
            tick_size=command.rules.tick_size,
            lot_size=command.rules.lot_size,
            multiplier=command.rules.multiplier,
            board_segment=command.rules.board_segment,
            lifecycle_state=command.rules.lifecycle_state,
        ),
        TradingRuleSet(
            instrument_id=iid,
            as_of_date=command.trade_date,
            settlement_cycle=command.rules.settlement_cycle,
            fund_settlement_cycle=0,
            price_limit_pct=command.rules.price_limit_pct,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        ),
        FeeSchedule(
            instrument_id=iid,
            as_of_date=command.trade_date,
            commission_rate=command.rules.commission_rate,
            min_commission=command.rules.min_commission,
            stamp_duty_rate=command.rules.stamp_duty_rate,
            transfer_fee_rate=command.rules.transfer_fee_rate,
        ),
    )
    return _ResolvedPaperInputs(
        order=Order(
            client_id=ClientOrderId(value=command.order_id),
            instrument_id=iid,
            order_type=OrderType(command.order_type),
            direction=OrderSide(command.side),
            quantity=command.quantity,
            price=command.price,
            trade_date=command.trade_date,
        ),
        lineage=lineage,
        rules=rules,
        assumption=FillAssumption(
            assumption_id=command.assumption.assumption_id,
            version=command.assumption.version,
            reference_price_field=command.assumption.reference_price_field,
            slippage_bps=command.assumption.slippage_bps,
        ),
    )


def _execution_id(session_id: str, idempotency_key: str) -> str:
    digest = sha256(f"{session_id}\x00{idempotency_key}".encode()).hexdigest()
    return f"paper-execution:{digest[:32]}"


def _ledger_event_id(execution_id: str) -> str:
    return f"account-event:{sha256(execution_id.encode()).hexdigest()[:32]}"


def _account_event(
    *,
    record: PaperExecutionRecord,
    account: AccountDefinition,
    event_id: str,
    idempotency_key: str,
) -> AccountEvent:
    fill = record.result.fill
    if fill is None:
        raise AppProcessError("paper execution has no fill to ledger")
    event_type = (
        AccountEventType.BUY if fill.direction.value == "buy" else AccountEventType.SELL
    )
    return create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=event_type,
            event_id=event_id,
            trade_date=fill.trade_date,
            settlement_date=fill.settlement_date,
            recorded_at=fill.event_time,
            idempotency_key=idempotency_key,
            actor=f"paper-session:{record.session_id}",
            source=AccountEventSource.PAPER_ENGINE,
            instrument_id=fill.instrument_id,
            quantity=Decimal(str(fill.quantity)),
            price=Decimal(str(fill.fill_price)),
            fees=Decimal(str(fill.commission + fill.transfer_fee)),
            tax=Decimal(str(fill.tax)),
            external_reference=record.execution_id,
            note=(
                f"assumption={fill.assumption_hash};"
                f"market_lineage={fill.market_lineage_hash}"
            ),
        ),
    )
