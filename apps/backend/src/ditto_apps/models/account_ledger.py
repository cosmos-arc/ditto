"""Strict HTTP DTOs for the immutable MANUAL account ledger."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from ditto_kernel.identity import InstrumentId
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AccountCommandReceiptResponse",
    "AccountEventResponse",
    "AccountLedgerResponse",
    "AccountResponse",
    "CashSnapshotResponse",
    "CorrectManualEventBody",
    "CreateManualAccountBody",
    "HistoryPointResponse",
    "HistoryQualityResponse",
    "HistorySegmentResponse",
    "LedgerRevisionResponse",
    "ManualAccountCatalogEntryResponse",
    "ManualAccountCatalogResponse",
    "ManualEventBody",
    "ManualHistoryQueryParams",
    "ManualHistoryResponse",
    "PortfolioPositionSnapshotResponse",
    "PortfolioSnapshotResponse",
    "ReverseManualEventBody",
]

_REQUEST_CONFIG = ConfigDict(strict=True, extra="forbid")
_RESPONSE_CONFIG = ConfigDict(strict=True, frozen=True, from_attributes=True)

type ManualBusinessEventType = Literal[
    "opening_cash",
    "opening_position",
    "buy",
    "sell",
    "deposit",
    "withdrawal",
    "fee",
    "tax",
    "interest",
    "dividend",
    "transfer_in",
    "transfer_out",
    "split",
    "merge",
    "other_corporate_action",
]
type AccountEventTypeResponse = Literal[
    "opening_cash",
    "opening_position",
    "buy",
    "sell",
    "deposit",
    "withdrawal",
    "fee",
    "tax",
    "interest",
    "dividend",
    "transfer_in",
    "transfer_out",
    "split",
    "merge",
    "other_corporate_action",
    "reversal",
    "correction",
]


class CreateManualAccountBody(BaseModel):
    """Create one permanently MANUAL account identity."""

    model_config = _REQUEST_CONFIG

    account_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    opened_at: datetime = Field(strict=False)
    currency: Literal["CNY"] = "CNY"


class ManualEventBody(BaseModel):
    """One business event; control events use dedicated endpoints."""

    model_config = _REQUEST_CONFIG

    event_type: ManualBusinessEventType
    trade_date: date = Field(strict=False)
    settlement_date: date = Field(strict=False)
    idempotency_key: str = Field(min_length=1, max_length=256)
    actor: str = Field(min_length=1, max_length=256)
    instrument_id: InstrumentId | None = Field(default=None, gt=0)
    quantity: Decimal = Field(default=Decimal("0"), ge=0, strict=False)
    price: Decimal = Field(default=Decimal("0"), ge=0, strict=False)
    gross_amount: Decimal = Field(default=Decimal("0"), ge=0, strict=False)
    fees: Decimal = Field(default=Decimal("0"), ge=0, strict=False)
    tax: Decimal = Field(default=Decimal("0"), ge=0, strict=False)
    net_cash: Decimal | None = Field(default=None, strict=False)
    flow_position: Literal["start_of_day", "end_of_day", "intraday"] | None = None
    note: str = Field(default="", max_length=4000)
    attachment_refs: tuple[str, ...] = Field(default=(), strict=False)
    external_reference: str | None = Field(default=None, max_length=512)


class CorrectManualEventBody(BaseModel):
    """Append a correction that replaces one prior business event."""

    model_config = _REQUEST_CONFIG

    corrects_event_id: str = Field(min_length=1, max_length=256)
    replacement: ManualEventBody


class ReverseManualEventBody(BaseModel):
    """Append a zero-effect control event reversing one prior event."""

    model_config = _REQUEST_CONFIG

    reverses_event_id: str = Field(min_length=1, max_length=256)
    trade_date: date = Field(strict=False)
    settlement_date: date = Field(strict=False)
    idempotency_key: str = Field(min_length=1, max_length=256)
    actor: str = Field(min_length=1, max_length=256)
    note: str = Field(default="", max_length=4000)


class AccountResponse(BaseModel):
    """Read-only account identity displayed on every account surface."""

    model_config = _RESPONSE_CONFIG

    account_id: str
    kind: Literal["manual"]
    name: str
    opened_at: datetime
    currency: Literal["CNY"]


class ManualAccountCatalogEntryResponse(BaseModel):
    """One selectable MANUAL account identity."""

    model_config = _RESPONSE_CONFIG

    account_id: str
    account_kind: Literal["manual"]
    account_name: str
    opened_at: datetime
    currency: Literal["CNY"]


class ManualAccountCatalogResponse(BaseModel):
    """Every MANUAL account in deterministic id order."""

    model_config = _RESPONSE_CONFIG

    accounts: tuple[ManualAccountCatalogEntryResponse, ...]


class AccountEventResponse(BaseModel):
    """Canonical immutable event and its tamper-evident hash."""

    model_config = _RESPONSE_CONFIG

    event_id: str
    account_id: str
    account_kind: Literal["manual"]
    event_type: AccountEventTypeResponse
    trade_date: str
    settlement_date: str
    recorded_at: datetime
    idempotency_key: str
    actor: str
    source: Literal["manual_entry", "file_import"]
    instrument_id: InstrumentId | None
    currency: Literal["CNY"]
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    fees: Decimal
    tax: Decimal
    net_cash: Decimal
    flow_position: Literal["start_of_day", "end_of_day", "intraday"] | None = None
    note: str
    attachment_refs: tuple[str, ...]
    external_reference: str | None
    reverses_event_id: str | None
    corrects_event_id: str | None
    replacement_event_type: ManualBusinessEventType | None
    event_hash: str


class AccountCommandReceiptResponse(BaseModel):
    """Immutable account command receipt with replay status."""

    model_config = _RESPONSE_CONFIG

    account: AccountResponse
    status: Literal["created", "replayed"]
    event: AccountEventResponse | None


class CashSnapshotResponse(BaseModel):
    """Available, settled, and frozen CNY balances."""

    model_config = _RESPONSE_CONFIG

    available: Decimal
    settled: Decimal
    frozen: Decimal
    total: Decimal


class PortfolioPositionSnapshotResponse(BaseModel):
    """One rebuilt holding with settlement-aware availability."""

    model_config = _RESPONSE_CONFIG

    instrument_id: InstrumentId
    quantity: Decimal
    available_quantity: Decimal
    average_cost: Decimal
    last_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal


class PortfolioSnapshotResponse(BaseModel):
    """Full-replay portfolio projection at one explicit date."""

    model_config = _RESPONSE_CONFIG

    account_id: str
    account_kind: Literal["manual"]
    as_of: str
    currency: Literal["CNY"]
    cash: CashSnapshotResponse
    positions: tuple[PortfolioPositionSnapshotResponse, ...]
    total_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal
    event_count: int
    ledger_hash: str
    valuation_complete: bool


class AccountLedgerResponse(BaseModel):
    """Account identity, visible immutable events, and rebuilt projection."""

    model_config = _RESPONSE_CONFIG

    account: AccountResponse
    events: tuple[AccountEventResponse, ...]
    snapshot: PortfolioSnapshotResponse
    ledger_revision: LedgerRevisionResponse


class LedgerRevisionResponse(BaseModel):
    """Append-order prefix identity of the complete ledger stream."""

    model_config = _RESPONSE_CONFIG

    event_count: int
    ledger_hash: str


_QUERY_CONFIG = ConfigDict(extra="forbid")


class ManualHistoryQueryParams(BaseModel):
    """
    GET query identity for one exact MANUAL historical series.

    Query strings arrive as plain text, so coercion stays lax here; the
    application query still rejects every invalid identity fail-closed.
    """

    model_config = _QUERY_CONFIG

    start_date: date = Field(strict=False)
    end_date: date = Field(strict=False)
    knowledge_cutoff: datetime = Field(strict=False)
    publication_cutoff: datetime = Field(strict=False)
    source_snapshot_ids: tuple[str, ...] = Field(min_length=1, strict=False)
    ledger_event_count: int = Field(ge=1, strict=False)
    ledger_hash: str = Field(min_length=1)


class HistoryQualityResponse(BaseModel):
    """One machine-readable quality or absence mark."""

    model_config = _RESPONSE_CONFIG

    code: str
    detail: str = ""


class HistoryPointResponse(BaseModel):
    """One dated valuation row; missing prices leave value gaps."""

    model_config = _RESPONSE_CONFIG

    on_date: str
    valuation_instant: str
    total_value: Decimal | None
    cash: Decimal | None
    external_flow: Decimal
    period_return: Decimal | None
    cumulative_return: Decimal | None
    segment_id: int | None
    price_time: str | None
    stale: bool
    source_snapshot_ids: tuple[str, ...]
    quality: tuple[HistoryQualityResponse, ...]


class HistorySegmentResponse(BaseModel):
    """One continuous positive-capital run with its own linked TWR."""

    model_config = _RESPONSE_CONFIG

    segment_id: int
    start_date: str
    end_date: str
    start_value: Decimal
    end_value: Decimal
    linked_return: Decimal | None
    closed_reason: Literal[
        "range_end",
        "loss_to_zero",
        "full_withdrawal",
        "valuation_gap",
        "negative_equity",
    ]
    quality: tuple[HistoryQualityResponse, ...]


class ManualHistoryResponse(BaseModel):
    """Complete replayable historical result for one MANUAL account."""

    model_config = _RESPONSE_CONFIG

    result_id: str
    account_id: str
    currency: Literal["CNY"]
    start_date: str
    end_date: str
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    ledger_revision: LedgerRevisionResponse
    method: str
    valuation_policy_version: str
    points: tuple[HistoryPointResponse, ...]
    segments: tuple[HistorySegmentResponse, ...]
