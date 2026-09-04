"""Account-ledger commands and idempotent MANUAL event orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from ditto_kernel.identity import InstrumentId
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
from ditto_portfolio.account_projection import AccountLedgerRebuilder

from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppNotFoundError,
)

__all__ = [
    "AccountCommandReceipt",
    "CorrectManualEventCommand",
    "CreateAccountCommand",
    "CreateAccountHandler",
    "ManualAccountCommandHandler",
    "ManualEventInput",
    "RecordManualEventCommand",
    "ReverseManualEventCommand",
    "TradeEventTerms",
]


@dataclass(frozen=True, kw_only=True)
class CreateAccountCommand:
    """Create one permanently typed portfolio/account identity."""

    account_id: str
    kind: AccountKind
    name: str
    opened_at: datetime
    currency: str = "CNY"

    @classmethod
    def manual(
        cls,
        *,
        account_id: str,
        name: str,
        opened_at: datetime,
        currency: str = "CNY",
    ) -> CreateAccountCommand:
        """Build the application-owned MANUAL account creation contract."""
        return cls(
            account_id=account_id,
            kind=AccountKind.MANUAL,
            name=name,
            opened_at=opened_at,
            currency=currency,
        )

    @classmethod
    def paper(
        cls,
        *,
        account_id: str,
        name: str,
        opened_at: datetime,
        currency: str = "CNY",
    ) -> CreateAccountCommand:
        """Build the application-owned PAPER account creation contract."""
        return cls(
            account_id=account_id,
            kind=AccountKind.PAPER,
            name=name,
            opened_at=opened_at,
            currency=currency,
        )


@dataclass(frozen=True, kw_only=True)
class TradeEventTerms:
    """Money-precise terms for one manually recorded trade."""

    quantity: Decimal
    price: Decimal
    fees: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")


@dataclass(frozen=True, kw_only=True)
class ManualEventInput:
    """User-authored business payload; immutable identity is host-derived."""

    event_type: AccountEventType
    trade_date: str
    settlement_date: str
    idempotency_key: str
    actor: str
    instrument_id: InstrumentId | None = None
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    gross_amount: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    net_cash: Decimal | None = None
    note: str = ""
    attachment_refs: tuple[str, ...] = ()
    external_reference: str | None = None

    @staticmethod
    def parse_business_event_type(event_type: str) -> AccountEventType:
        """Parse one named business event without host capability imports."""
        try:
            resolved_type = AccountEventType(event_type)
        except ValueError as exc:
            raise AppCommandError(f"unknown account event type: {event_type}") from exc
        if resolved_type in {AccountEventType.CORRECTION, AccountEventType.REVERSAL}:
            raise AppCommandError("business event cannot be a control event")
        return resolved_type

    @classmethod
    def buy_or_sell(
        cls,
        *,
        side: Literal["buy", "sell"],
        trade_date: str,
        settlement_date: str,
        idempotency_key: str,
        actor: str,
        instrument_id: InstrumentId,
        terms: TradeEventTerms,
    ) -> ManualEventInput:
        """Build an explicit BUY or SELL input."""
        return cls(
            event_type=(
                AccountEventType.BUY if side == "buy" else AccountEventType.SELL
            ),
            trade_date=trade_date,
            settlement_date=settlement_date,
            idempotency_key=idempotency_key,
            actor=actor,
            instrument_id=instrument_id,
            quantity=terms.quantity,
            price=terms.price,
            fees=terms.fees,
            tax=terms.tax,
        )

    @classmethod
    def cash(
        cls,
        *,
        event_type: Literal[
            "opening_cash",
            "deposit",
            "withdrawal",
            "fee",
            "tax",
            "interest",
        ],
        trade_date: str,
        settlement_date: str,
        idempotency_key: str,
        actor: str,
        amount: Decimal,
    ) -> ManualEventInput:
        """Build a cash-only manual event."""
        return cls(
            event_type=AccountEventType(event_type),
            trade_date=trade_date,
            settlement_date=settlement_date,
            idempotency_key=idempotency_key,
            actor=actor,
            gross_amount=amount,
        )


@dataclass(frozen=True, kw_only=True)
class RecordManualEventCommand:
    """Append one MANUAL business event."""

    account_id: str
    event: ManualEventInput


@dataclass(frozen=True, kw_only=True)
class CorrectManualEventCommand:
    """Append a correction that replaces one prior business event."""

    account_id: str
    corrects_event_id: str
    replacement: ManualEventInput


@dataclass(frozen=True, kw_only=True)
class ReverseManualEventCommand:
    """Append a reversal of one prior event."""

    account_id: str
    reverses_event_id: str
    trade_date: str
    settlement_date: str
    idempotency_key: str
    actor: str
    note: str = ""


@dataclass(frozen=True, kw_only=True)
class AccountCommandReceipt:
    """Immutable command receipt."""

    account: AccountDefinition
    status: Literal["created", "replayed"]
    event: AccountEvent | None = None


class CreateAccountHandler:
    """Idempotently create immutable account identities."""

    def __init__(self, *, journal: AccountEventJournalPort) -> None:
        self._journal = journal

    def handle(self, command: CreateAccountCommand) -> AccountCommandReceipt:
        """Create an identity or return an exact replay receipt."""
        try:
            requested = AccountDefinition(
                account_id=command.account_id,
                kind=command.kind,
                name=command.name,
                opened_at=command.opened_at,
                currency=command.currency,
            )
        except AccountLedgerError as exc:
            raise AppCommandError(str(exc)) from exc
        existing = self._journal.get_account(command.account_id)
        if existing is not None:
            if existing != requested:
                raise AppConflictError(
                    f"account immutable identity conflict: {command.account_id}"
                )
            return AccountCommandReceipt(account=existing, status="replayed")
        created = self._journal.create_account(requested)
        return AccountCommandReceipt(account=created, status="created")


class ManualAccountCommandHandler:
    """Record, correct, and reverse MANUAL events through the journal port."""

    def __init__(
        self,
        *,
        journal: AccountEventJournalPort,
        clock: Callable[[], datetime],
        rebuilder: AccountLedgerRebuilder | None = None,
    ) -> None:
        self._journal = journal
        self._clock = clock
        self._rebuilder = rebuilder or AccountLedgerRebuilder()

    def record(self, command: RecordManualEventCommand) -> AccountCommandReceipt:
        """Append one normal business event with exact idempotency."""
        if command.event.event_type in {
            AccountEventType.CORRECTION,
            AccountEventType.REVERSAL,
        }:
            raise AppCommandError("record command accepts business events only")
        account = self._manual_account(command.account_id)
        return self._append(
            account=account,
            input_=command.event,
            event_type=command.event.event_type,
        )

    def correct(self, command: CorrectManualEventCommand) -> AccountCommandReceipt:
        """Append a correction while retaining the superseded event."""
        account = self._manual_account(command.account_id)
        target = self._journal.get_event(
            command.account_id,
            command.corrects_event_id,
        )
        if target is None:
            raise AppNotFoundError(f"event not found: {command.corrects_event_id}")
        if target.event_type in {
            AccountEventType.CORRECTION,
            AccountEventType.REVERSAL,
        }:
            raise AppConflictError("correction target must be a business event")
        return self._append(
            account=account,
            input_=command.replacement,
            event_type=AccountEventType.CORRECTION,
            corrects_event_id=target.event_id,
            replacement_event_type=command.replacement.event_type,
        )

    def reverse(self, command: ReverseManualEventCommand) -> AccountCommandReceipt:
        """Append a reversal while retaining the referenced event."""
        account = self._manual_account(command.account_id)
        target = self._journal.get_event(
            command.account_id,
            command.reverses_event_id,
        )
        if target is None:
            raise AppNotFoundError(f"event not found: {command.reverses_event_id}")
        input_ = ManualEventInput(
            event_type=AccountEventType.REVERSAL,
            trade_date=command.trade_date,
            settlement_date=command.settlement_date,
            idempotency_key=command.idempotency_key,
            actor=command.actor,
            note=command.note,
        )
        return self._append(
            account=account,
            input_=input_,
            event_type=AccountEventType.REVERSAL,
            reverses_event_id=target.event_id,
        )

    def _manual_account(self, account_id: str) -> AccountDefinition:
        account = self._journal.get_account(account_id)
        if account is None:
            raise AppNotFoundError(f"account not found: {account_id}")
        if account.kind is not AccountKind.MANUAL:
            raise AppConflictError(f"account is not a MANUAL account: {account_id}")
        return account

    def _append(
        self,
        *,
        account: AccountDefinition,
        input_: ManualEventInput,
        event_type: AccountEventType,
        reverses_event_id: str | None = None,
        corrects_event_id: str | None = None,
        replacement_event_type: AccountEventType | None = None,
    ) -> AccountCommandReceipt:
        existing = self._journal.find_by_idempotency_key(
            account.account_id,
            input_.idempotency_key,
        )
        recorded_at = existing.recorded_at if existing is not None else self._clock()
        event_id = (
            existing.event_id
            if existing is not None
            else _event_id(account.account_id, input_.idempotency_key)
        )
        try:
            event = create_account_event(
                account=account,
                draft=_event_draft(
                    input_=input_,
                    event_type=event_type,
                    event_id=event_id,
                    recorded_at=recorded_at,
                    reverses_event_id=reverses_event_id,
                    corrects_event_id=corrects_event_id,
                    replacement_event_type=replacement_event_type,
                ),
            )
            if existing is not None:
                if existing.event_hash != event.event_hash:
                    raise AppConflictError(
                        f"idempotency_key payload conflict: {input_.idempotency_key}"
                    )
                return AccountCommandReceipt(
                    account=account,
                    event=existing,
                    status="replayed",
                )
            events = (*self._journal.list_events(account.account_id), event)
            as_of = max(item.trade_date for item in events)
            self._rebuilder.rebuild(account=account, events=events, as_of=as_of)
        except AccountLedgerError as exc:
            raise AppCommandError(str(exc)) from exc
        created = self._journal.append(event)
        return AccountCommandReceipt(
            account=account,
            event=created,
            status="created",
        )


def _event_draft(
    *,
    input_: ManualEventInput,
    event_type: AccountEventType,
    event_id: str,
    recorded_at: datetime,
    reverses_event_id: str | None,
    corrects_event_id: str | None,
    replacement_event_type: AccountEventType | None,
) -> AccountEventDraft:
    return AccountEventDraft(
        event_type=event_type,
        event_id=event_id,
        trade_date=input_.trade_date,
        settlement_date=input_.settlement_date,
        recorded_at=recorded_at,
        idempotency_key=input_.idempotency_key,
        actor=input_.actor,
        source=AccountEventSource.MANUAL_ENTRY,
        instrument_id=input_.instrument_id,
        quantity=input_.quantity,
        price=input_.price,
        gross_amount=input_.gross_amount,
        fees=input_.fees,
        tax=input_.tax,
        net_cash=input_.net_cash,
        note=input_.note,
        attachment_refs=input_.attachment_refs,
        external_reference=input_.external_reference,
        reverses_event_id=reverses_event_id,
        corrects_event_id=corrects_event_id,
        replacement_event_type=replacement_event_type,
    )


def _event_id(account_id: str, idempotency_key: str) -> str:
    digest = sha256(f"{account_id}\x00{idempotency_key}".encode()).hexdigest()
    return f"account-event:{digest[:32]}"
