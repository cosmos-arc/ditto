"""
Append-only account ledger contracts and canonical event construction.

The three account kinds are deliberately distinct facts:

* ``MODEL`` is a versioned target portfolio and never accepts ledger events.
* ``PAPER`` is driven by the system's simulated execution facts.
* ``MANUAL`` is driven by user-recorded external-account facts.

Persistence belongs to execution. This module owns immutable event contracts,
validation, hashing, and the journal port; projections live in account_projection.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from typing import Protocol, cast, runtime_checkable

from ditto_kernel.identity import InstrumentId

from ditto_portfolio.errors import PortfolioError

__all__ = [
    "AccountDefinition",
    "AccountEvent",
    "AccountEventDraft",
    "AccountEventJournalPort",
    "AccountEventSource",
    "AccountEventType",
    "AccountKind",
    "AccountLedgerError",
    "ManualAccountEvent",
    "ManualCorrectionEvent",
    "ManualLedgerEvent",
    "ManualReversalEvent",
    "create_account_event",
]


_MONEY_QUANTUM = Decimal("0.01")
_PRICE_QUANTUM = Decimal("0.0001")
_QUANTITY_QUANTUM = Decimal("0.0001")
_ZERO = Decimal("0")


class AccountLedgerError(PortfolioError):
    """The immutable account-ledger contract was violated."""


class AccountKind(StrEnum):
    """Permanent semantic identity of a portfolio/account."""

    MODEL = "model"
    PAPER = "paper"
    MANUAL = "manual"


class AccountEventSource(StrEnum):
    """Authority that produced an account event."""

    MANUAL_ENTRY = "manual_entry"
    FILE_IMPORT = "file_import"
    PAPER_ENGINE = "paper_engine"


class AccountEventType(StrEnum):
    """Append-only v1 account event vocabulary."""

    OPENING_CASH = "opening_cash"
    OPENING_POSITION = "opening_position"
    BUY = "buy"
    SELL = "sell"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    TAX = "tax"
    INTEREST = "interest"
    DIVIDEND = "dividend"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    SPLIT = "split"
    MERGE = "merge"
    OTHER_CORPORATE_ACTION = "other_corporate_action"
    REVERSAL = "reversal"
    CORRECTION = "correction"


_TRADE_TYPES = frozenset({AccountEventType.BUY, AccountEventType.SELL})
_POSITION_IN_TYPES = frozenset(
    {AccountEventType.OPENING_POSITION, AccountEventType.TRANSFER_IN}
)
_POSITION_OUT_TYPES = frozenset({AccountEventType.TRANSFER_OUT})
_CASH_IN_TYPES = frozenset(
    {
        AccountEventType.OPENING_CASH,
        AccountEventType.DEPOSIT,
        AccountEventType.INTEREST,
        AccountEventType.DIVIDEND,
    }
)
_CASH_OUT_TYPES = frozenset(
    {AccountEventType.WITHDRAWAL, AccountEventType.FEE, AccountEventType.TAX}
)
_CORPORATE_ACTION_TYPES = frozenset(
    {
        AccountEventType.SPLIT,
        AccountEventType.MERGE,
        AccountEventType.OTHER_CORPORATE_ACTION,
    }
)
_BUSINESS_TYPES = (
    _TRADE_TYPES
    | _POSITION_IN_TYPES
    | _POSITION_OUT_TYPES
    | _CASH_IN_TYPES
    | _CASH_OUT_TYPES
    | _CORPORATE_ACTION_TYPES
)

# Cross-module implementation support for ``account_projection``.  These names
# intentionally stay out of ``__all__``: they are stable inside the portfolio
# package without becoming part of the account-ledger public contract.
LEDGER_ZERO = _ZERO
LEDGER_TRADE_TYPES = _TRADE_TYPES
LEDGER_POSITION_IN_TYPES = _POSITION_IN_TYPES
LEDGER_POSITION_OUT_TYPES = _POSITION_OUT_TYPES
LEDGER_CASH_IN_TYPES = _CASH_IN_TYPES
LEDGER_CASH_OUT_TYPES = _CASH_OUT_TYPES
LEDGER_CORPORATE_ACTION_TYPES = _CORPORATE_ACTION_TYPES
LEDGER_BUSINESS_TYPES = _BUSINESS_TYPES


@dataclass(frozen=True, kw_only=True)
class AccountDefinition:
    """Immutable account identity; changing kind means creating another account."""

    account_id: str
    kind: AccountKind
    name: str
    opened_at: datetime
    currency: str = "CNY"

    def __post_init__(self) -> None:
        """Validate immutable account identity fields."""
        if not self.account_id.strip():
            raise AccountLedgerError("account_id must be non-empty")
        if not self.name.strip():
            raise AccountLedgerError("account name must be non-empty")
        if self.opened_at.tzinfo is None:
            raise AccountLedgerError("opened_at must be timezone-aware")
        if self.currency != "CNY":
            raise AccountLedgerError("v1 account currency must be CNY")

    def assert_accepts(self, event: AccountEvent) -> None:
        """Reject implicit account conversion or cross-account event mixing."""
        if event.account_id != self.account_id:
            raise AccountLedgerError("account_id mismatch")
        if event.account_kind is not self.kind:
            raise AccountLedgerError("account kind mismatch")
        if self.kind is AccountKind.MODEL:
            raise AccountLedgerError("MODEL portfolios do not accept ledger events")
        expected_source = (
            AccountEventSource.PAPER_ENGINE if self.kind is AccountKind.PAPER else None
        )
        if expected_source is not None and event.source is not expected_source:
            raise AccountLedgerError("PAPER events must come from paper_engine")
        if (
            self.kind is AccountKind.MANUAL
            and event.source is AccountEventSource.PAPER_ENGINE
        ):
            raise AccountLedgerError("MANUAL events cannot come from paper_engine")


@dataclass(frozen=True, kw_only=True)
class AccountEventDraft:
    """Unhashed event payload accepted by :func:`create_account_event`."""

    event_type: AccountEventType
    event_id: str
    trade_date: str
    settlement_date: str
    recorded_at: datetime
    idempotency_key: str
    actor: str
    source: AccountEventSource
    instrument_id: InstrumentId | None = None
    currency: str = "CNY"
    quantity: Decimal = _ZERO
    price: Decimal = _ZERO
    gross_amount: Decimal = _ZERO
    fees: Decimal = _ZERO
    tax: Decimal = _ZERO
    net_cash: Decimal | None = None
    note: str = ""
    attachment_refs: tuple[str, ...] = ()
    external_reference: str | None = None
    reverses_event_id: str | None = None
    corrects_event_id: str | None = None
    replacement_event_type: AccountEventType | None = None


@dataclass(frozen=True, kw_only=True)
class AccountEvent:
    """Canonical immutable ledger event shared by PAPER and MANUAL accounts."""

    event_id: str
    account_id: str
    account_kind: AccountKind
    event_type: AccountEventType
    trade_date: str
    settlement_date: str
    recorded_at: datetime
    idempotency_key: str
    actor: str
    source: AccountEventSource
    instrument_id: InstrumentId | None
    currency: str
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    fees: Decimal
    tax: Decimal
    net_cash: Decimal
    note: str
    attachment_refs: tuple[str, ...]
    external_reference: str | None
    reverses_event_id: str | None
    corrects_event_id: str | None
    replacement_event_type: AccountEventType | None
    event_hash: str


@dataclass(frozen=True, kw_only=True)
class ManualLedgerEvent(AccountEvent):
    """A normal MANUAL account business event."""


@dataclass(frozen=True, kw_only=True)
class ManualReversalEvent(AccountEvent):
    """An append-only reversal referencing a prior event."""


@dataclass(frozen=True, kw_only=True)
class ManualCorrectionEvent(AccountEvent):
    """An append-only replacement for a prior business event."""


type ManualAccountEvent = (
    ManualLedgerEvent | ManualReversalEvent | ManualCorrectionEvent
)


@runtime_checkable
class AccountEventJournalPort(Protocol):
    """Persistence-neutral append-only account journal contract."""

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        """Create an immutable account identity, or return the exact existing one."""
        ...

    def get_account(self, account_id: str) -> AccountDefinition | None:
        """Read one exact account identity."""
        ...

    def append(self, event: AccountEvent) -> AccountEvent:
        """Append one event atomically; existing rows may never be overwritten."""
        ...

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        """Read one exact immutable event."""
        ...

    def find_by_idempotency_key(
        self,
        account_id: str,
        idempotency_key: str,
    ) -> AccountEvent | None:
        """Resolve an idempotent command receipt."""
        ...

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        """Read the complete event stream in append order."""
        ...


def create_account_event(
    *,
    account: AccountDefinition,
    draft: AccountEventDraft,
) -> AccountEvent:
    """Validate, normalize, and hash an account event."""
    normalized_quantity = _quantity(draft.quantity)
    normalized_price = _price(draft.price)
    normalized_fees = _money(draft.fees)
    normalized_tax = _money(draft.tax)
    normalized_gross = _money(draft.gross_amount)
    effective_type = draft.replacement_event_type or draft.event_type
    if (
        effective_type in _TRADE_TYPES
        and normalized_gross == _ZERO
        and normalized_quantity > _ZERO
        and normalized_price > _ZERO
    ):
        normalized_gross = _money(normalized_quantity * normalized_price)
    normalized_net_cash = (
        _derived_net_cash(
            effective_type,
            gross_amount=normalized_gross,
            fees=normalized_fees,
            tax=normalized_tax,
        )
        if draft.net_cash is None
        else _money(draft.net_cash)
    )
    values: dict[str, object] = {
        "event_id": draft.event_id,
        "account_id": account.account_id,
        "account_kind": account.kind,
        "event_type": draft.event_type,
        "trade_date": draft.trade_date,
        "settlement_date": draft.settlement_date,
        "recorded_at": draft.recorded_at,
        "idempotency_key": draft.idempotency_key,
        "actor": draft.actor,
        "source": draft.source,
        "instrument_id": draft.instrument_id,
        "currency": draft.currency,
        "quantity": normalized_quantity,
        "price": normalized_price,
        "gross_amount": normalized_gross,
        "fees": normalized_fees,
        "tax": normalized_tax,
        "net_cash": normalized_net_cash,
        "note": draft.note,
        "attachment_refs": tuple(draft.attachment_refs),
        "external_reference": draft.external_reference,
        "reverses_event_id": draft.reverses_event_id,
        "corrects_event_id": draft.corrects_event_id,
        "replacement_event_type": draft.replacement_event_type,
    }
    _validate_event_values(values)
    event_hash = _event_hash(values)
    event_class: type[AccountEvent]
    if account.kind is AccountKind.MANUAL:
        if draft.event_type is AccountEventType.REVERSAL:
            event_class = ManualReversalEvent
        elif draft.event_type is AccountEventType.CORRECTION:
            event_class = ManualCorrectionEvent
        else:
            event_class = ManualLedgerEvent
    else:
        event_class = AccountEvent
    event = event_class(
        event_id=draft.event_id,
        account_id=account.account_id,
        account_kind=account.kind,
        event_type=draft.event_type,
        trade_date=draft.trade_date,
        settlement_date=draft.settlement_date,
        recorded_at=draft.recorded_at,
        idempotency_key=draft.idempotency_key,
        actor=draft.actor,
        source=draft.source,
        instrument_id=draft.instrument_id,
        currency=draft.currency,
        quantity=normalized_quantity,
        price=normalized_price,
        gross_amount=normalized_gross,
        fees=normalized_fees,
        tax=normalized_tax,
        net_cash=normalized_net_cash,
        note=draft.note,
        attachment_refs=tuple(draft.attachment_refs),
        external_reference=draft.external_reference,
        reverses_event_id=draft.reverses_event_id,
        corrects_event_id=draft.corrects_event_id,
        replacement_event_type=draft.replacement_event_type,
        event_hash=event_hash,
    )
    account.assert_accepts(event)
    return event


def _validate_event_values(values: Mapping[str, object]) -> None:
    _validate_common_event_fields(values)
    event_type = values["event_type"]
    if not isinstance(event_type, AccountEventType):
        raise AccountLedgerError("event_type is invalid")
    if event_type is AccountEventType.REVERSAL:
        _validate_reversal(values)
        return
    if event_type is AccountEventType.CORRECTION:
        _validate_correction(values)
        return
    _validate_plain_business_event(event_type, values)


def _validate_common_event_fields(values: Mapping[str, object]) -> None:
    event_id = str(values["event_id"])
    if not event_id.strip():
        raise AccountLedgerError("event_id must be non-empty")
    if not str(values["idempotency_key"]).strip():
        raise AccountLedgerError("idempotency_key must be non-empty")
    if not str(values["actor"]).strip():
        raise AccountLedgerError("actor must be non-empty")
    trade_date = _parse_date(str(values["trade_date"]), "trade_date")
    settlement_date = _parse_date(
        str(values["settlement_date"]),
        "settlement_date",
    )
    if settlement_date < trade_date:
        raise AccountLedgerError("settlement_date cannot precede trade_date")
    recorded_at = values["recorded_at"]
    if not isinstance(recorded_at, datetime) or recorded_at.tzinfo is None:
        raise AccountLedgerError("recorded_at must be timezone-aware")
    if values["currency"] != "CNY":
        raise AccountLedgerError("v1 account event currency must be CNY")


def _validate_reversal(values: Mapping[str, object]) -> None:
    replacement_type = values["replacement_event_type"]
    if not values["reverses_event_id"]:
        raise AccountLedgerError("reverses_event_id is required")
    if values["corrects_event_id"] or replacement_type is not None:
        raise AccountLedgerError("reversal cannot carry correction fields")
    _require_zero_business_fields(values)


def _validate_correction(values: Mapping[str, object]) -> None:
    replacement_type = values["replacement_event_type"]
    if not values["corrects_event_id"]:
        raise AccountLedgerError("corrects_event_id is required")
    if values["reverses_event_id"]:
        raise AccountLedgerError("correction cannot carry reverses_event_id")
    if replacement_type is None:
        raise AccountLedgerError("replacement_event_type is required")
    if not isinstance(replacement_type, AccountEventType):
        raise AccountLedgerError("replacement_event_type is invalid")
    if replacement_type not in _BUSINESS_TYPES:
        raise AccountLedgerError("replacement_event_type must be a business event")
    _validate_business_fields(replacement_type, values)


def _validate_plain_business_event(
    event_type: AccountEventType,
    values: Mapping[str, object],
) -> None:
    if values["reverses_event_id"] or values["corrects_event_id"]:
        raise AccountLedgerError("business event cannot carry correction references")
    if values["replacement_event_type"] is not None:
        raise AccountLedgerError("business event cannot carry replacement_event_type")
    _validate_business_fields(event_type, values)


def _validate_business_fields(
    event_type: AccountEventType,
    values: Mapping[str, object],
) -> None:
    quantity = _as_decimal(values["quantity"], "quantity")
    price = _as_decimal(values["price"], "price")
    gross = _as_decimal(values["gross_amount"], "gross_amount")
    fees = _as_decimal(values["fees"], "fees")
    tax = _as_decimal(values["tax"], "tax")
    if any(value < _ZERO for value in (quantity, price, gross, fees, tax)):
        raise AccountLedgerError(
            "quantity, price, gross_amount, fees, and tax must be non-negative"
        )
    requires_instrument = (
        event_type
        in (
            _TRADE_TYPES
            | _POSITION_IN_TYPES
            | _POSITION_OUT_TYPES
            | _CORPORATE_ACTION_TYPES
        )
        or event_type is AccountEventType.DIVIDEND
    )
    if requires_instrument and values["instrument_id"] is None:
        raise AccountLedgerError(f"{event_type.value} requires instrument_id")
    if event_type in _TRADE_TYPES | _POSITION_IN_TYPES | _POSITION_OUT_TYPES:
        if quantity <= _ZERO:
            raise AccountLedgerError(f"{event_type.value} quantity must be positive")
        if price <= _ZERO:
            raise AccountLedgerError(f"{event_type.value} price must be positive")
    if event_type in _CASH_IN_TYPES | _CASH_OUT_TYPES and gross <= _ZERO:
        raise AccountLedgerError(f"{event_type.value} gross_amount must be positive")
    if event_type in _CORPORATE_ACTION_TYPES and quantity <= _ZERO:
        raise AccountLedgerError(f"{event_type.value} quantity must be positive")


def _require_zero_business_fields(values: Mapping[str, object]) -> None:
    for field_name in ("quantity", "price", "gross_amount", "fees", "tax", "net_cash"):
        if _as_decimal(values[field_name], field_name) != _ZERO:
            raise AccountLedgerError(f"reversal {field_name} must be zero")
    if values["instrument_id"] is not None:
        raise AccountLedgerError("reversal instrument_id must be empty")


def _derived_net_cash(
    event_type: AccountEventType,
    *,
    gross_amount: Decimal,
    fees: Decimal,
    tax: Decimal,
) -> Decimal:
    if event_type in {
        AccountEventType.OPENING_CASH,
        AccountEventType.DEPOSIT,
        AccountEventType.INTEREST,
        AccountEventType.DIVIDEND,
        AccountEventType.SELL,
    }:
        return _money(gross_amount - fees - tax)
    if event_type in {
        AccountEventType.WITHDRAWAL,
        AccountEventType.FEE,
        AccountEventType.TAX,
    }:
        return _money(-gross_amount - fees - tax)
    if event_type is AccountEventType.BUY:
        return _money(-gross_amount - fees - tax)
    return _money(_ZERO)


def _event_values(event: AccountEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "account_id": event.account_id,
        "account_kind": event.account_kind,
        "event_type": event.event_type,
        "trade_date": event.trade_date,
        "settlement_date": event.settlement_date,
        "recorded_at": event.recorded_at,
        "idempotency_key": event.idempotency_key,
        "actor": event.actor,
        "source": event.source,
        "instrument_id": event.instrument_id,
        "currency": event.currency,
        "quantity": event.quantity,
        "price": event.price,
        "gross_amount": event.gross_amount,
        "fees": event.fees,
        "tax": event.tax,
        "net_cash": event.net_cash,
        "note": event.note,
        "attachment_refs": event.attachment_refs,
        "external_reference": event.external_reference,
        "reverses_event_id": event.reverses_event_id,
        "corrects_event_id": event.corrects_event_id,
        "replacement_event_type": event.replacement_event_type,
    }


def _event_hash(values: Mapping[str, object]) -> str:
    canonical = {
        key: _canonical_value(value)
        for key, value in sorted(values.items(), key=lambda item: item[0])
    }
    digest = sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"account-event:sha256:{digest}"


def _ledger_hash(events: tuple[AccountEvent, ...]) -> str:
    digest = sha256()
    digest.update(b"account-ledger:v1")
    for event in events:
        digest.update(b"\x00")
        digest.update(event.event_hash.encode())
    return f"account-ledger:sha256:{digest.hexdigest()}"


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in cast("tuple[object, ...]", value)]
    if isinstance(value, int):
        return int(value)
    return value


def _money(value: Decimal) -> Decimal:
    return _as_decimal(value, "money").quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _price(value: Decimal) -> Decimal:
    return _as_decimal(value, "price").quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity(value: Decimal) -> Decimal:
    return (
        _as_decimal(value, "quantity")
        .quantize(
            _QUANTITY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        .normalize()
    )


def _as_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise AccountLedgerError(f"{field_name} must be Decimal")
    try:
        if not value.is_finite():
            raise AccountLedgerError(f"{field_name} must be finite")
    except InvalidOperation as exc:
        raise AccountLedgerError(f"{field_name} must be finite") from exc
    return value


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AccountLedgerError(f"{field_name} must be YYYY-MM-DD") from exc


# See the constant aliases above.  Keeping projection mechanics out of
# ``account_ledger`` avoids one oversized domain module while retaining a
# single canonical implementation for event hashing and decimal normalization.
ledger_event_values = _event_values
ledger_event_hash = _event_hash
ledger_hash = _ledger_hash
ledger_money = _money
ledger_price = _price
ledger_quantity = _quantity
ledger_parse_date = _parse_date
