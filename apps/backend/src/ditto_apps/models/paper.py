"""Strict HTTP DTOs for formal local paper trading."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from ditto_application.paper_contracts import PaperExecutionInfo
from ditto_kernel.identity import InstrumentId
from pydantic import BaseModel, ConfigDict, Field

from ditto_apps.models.account_ledger import (
    CashSnapshotResponse,
    PortfolioPositionSnapshotResponse,
)

__all__ = [
    "CreatePaperAccountBody",
    "CreatePaperSessionBody",
    "OperatePaperOrderBody",
    "PaperAccountLedgerResponse",
    "PaperAccountReceiptResponse",
    "PaperExecutionReceiptResponse",
    "PaperFillAssumptionBody",
    "PaperInstrumentRulesBody",
    "PaperMarketSnapshotBody",
    "PaperReconciliationResponse",
    "PaperRecoverResponse",
    "PaperSessionCommandResponse",
    "PaperSessionReadResponse",
    "PausePaperSessionBody",
    "ReconcilePaperSessionBody",
    "RecoverPaperSessionBody",
]

_REQUEST_CONFIG = ConfigDict(strict=True, extra="forbid")
_RESPONSE_CONFIG = ConfigDict(strict=True, frozen=True, from_attributes=True)


class CreatePaperAccountBody(BaseModel):
    """Create one permanently PAPER account with opening cash."""

    model_config = _REQUEST_CONFIG

    account_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    opened_at: datetime = Field(strict=False)
    trade_date: date = Field(strict=False)
    initial_cash: Decimal = Field(gt=0, strict=False)
    idempotency_key: str = Field(min_length=1, max_length=256)
    currency: Literal["CNY"] = "CNY"


class CreatePaperSessionBody(BaseModel):
    """Create and optionally start one paper session."""

    model_config = _REQUEST_CONFIG

    session_id: str = Field(min_length=1, max_length=128)
    account_id: str = Field(min_length=1, max_length=128)
    strategy_id: str = Field(min_length=1, max_length=128)
    trade_date: date = Field(strict=False)
    idempotency_key: str = Field(min_length=1, max_length=256)
    start_immediately: bool = True


class PausePaperSessionBody(BaseModel):
    """Pause a running paper session."""

    model_config = _REQUEST_CONFIG

    idempotency_key: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=1000)


class ReconcilePaperSessionBody(BaseModel):
    """Request one exact EOD reconciliation."""

    model_config = _REQUEST_CONFIG

    idempotency_key: str = Field(min_length=1, max_length=256)


class RecoverPaperSessionBody(BaseModel):
    """Request repair of persisted fills missing ledger markers."""

    model_config = _REQUEST_CONFIG

    idempotency_key: str = Field(min_length=1, max_length=256)


class PaperMarketSnapshotBody(BaseModel):
    """One market payload with explicit PIT provenance."""

    model_config = _REQUEST_CONFIG

    dataset_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    observed_at: datetime = Field(strict=False)
    publication_cutoff: datetime = Field(strict=False)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    prev_close: float = Field(gt=0)
    volume: float = Field(ge=0)
    amount: float = Field(ge=0)
    is_suspended: bool = False
    limit_up: float | None = Field(default=None, gt=0)
    limit_down: float | None = Field(default=None, gt=0)
    avg_volume_20d: float | None = Field(default=None, ge=0)


class PaperInstrumentRulesBody(BaseModel):
    """Exact static, trading, and fee rules used for one operation."""

    model_config = _REQUEST_CONFIG

    asset_class: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    tick_size: float = Field(gt=0)
    lot_size: int = Field(gt=0)
    board_segment: str = Field(min_length=1)
    settlement_cycle: int = Field(ge=0)
    commission_rate: float = Field(ge=0)
    min_commission: float = Field(ge=0)
    stamp_duty_rate: float = Field(ge=0)
    transfer_fee_rate: float = Field(ge=0)
    currency: Literal["CNY"] = "CNY"
    multiplier: float = Field(default=1.0, gt=0)
    lifecycle_state: str = "listed"
    price_limit_pct: float | None = Field(default=0.1, gt=0)


class PaperFillAssumptionBody(BaseModel):
    """Versioned price and slippage policy."""

    model_config = _REQUEST_CONFIG

    assumption_id: str = Field(min_length=1)
    version: int = Field(gt=0)
    reference_price_field: Literal["open", "close"]
    slippage_bps: float = Field(ge=0)


class OperatePaperOrderBody(BaseModel):
    """Complete deterministic order, market, rule, and assumption input."""

    model_config = _REQUEST_CONFIG

    idempotency_key: str = Field(min_length=1, max_length=256)
    order_id: str = Field(min_length=1, max_length=256)
    instrument_id: int = Field(gt=0)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: int = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    trade_date: date = Field(strict=False)
    settlement_date: date = Field(strict=False)
    decision_at: datetime = Field(strict=False)
    execution_at: datetime = Field(strict=False)
    position_quantity: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    market: PaperMarketSnapshotBody
    rules: PaperInstrumentRulesBody
    assumption: PaperFillAssumptionBody


class PaperAccountReceiptResponse(BaseModel):
    """PAPER account identity and opening event receipt."""

    model_config = _RESPONSE_CONFIG

    account_id: str
    account_kind: Literal["paper"]
    name: str
    status: Literal["created", "replayed"]
    opening_event_id: str | None


class PaperAccountIdentityResponse(BaseModel):
    """Read-only PAPER account identity."""

    model_config = _RESPONSE_CONFIG

    account_id: str
    account_kind: Literal["paper"] = Field(validation_alias="kind")
    name: str
    opened_at: datetime
    currency: Literal["CNY"]


class PaperLedgerEventResponse(BaseModel):
    """Immutable PAPER engine event and tamper-evident hash."""

    model_config = _RESPONSE_CONFIG

    event_id: str
    account_id: str
    account_kind: Literal["paper"]
    event_type: str
    trade_date: str
    settlement_date: str
    recorded_at: datetime
    idempotency_key: str
    actor: str
    source: Literal["paper_engine"]
    instrument_id: InstrumentId | None
    currency: Literal["CNY"]
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    fees: Decimal
    tax: Decimal
    net_cash: Decimal
    note: str
    external_reference: str | None
    event_hash: str


class PaperPortfolioSnapshotResponse(BaseModel):
    """Full replay of one PAPER account at an explicit date."""

    model_config = _RESPONSE_CONFIG

    account_id: str
    account_kind: Literal["paper"]
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


class PaperAccountLedgerResponse(BaseModel):
    """PAPER identity, events, and rebuilt projection."""

    model_config = _RESPONSE_CONFIG

    account: PaperAccountIdentityResponse
    events: tuple[PaperLedgerEventResponse, ...]
    snapshot: PaperPortfolioSnapshotResponse


class PaperSessionResponse(BaseModel):
    """Durable paper session state."""

    model_config = _RESPONSE_CONFIG

    session_id: str
    account_id: str
    strategy_id: str
    trade_date: str
    status: Literal["created", "running", "paused"]
    revision: int
    created_at: datetime
    updated_at: datetime
    pause_reason: str | None


class PaperSessionCommandResponse(BaseModel):
    """Lifecycle command receipt."""

    model_config = _RESPONSE_CONFIG

    status: Literal["created", "replayed"]
    action: str
    session: PaperSessionResponse


class PaperFillResponse(BaseModel):
    """Simulated fill economics and evidence hashes."""

    model_config = _RESPONSE_CONFIG

    fill_id: str
    order_id: str
    instrument_id: int
    direction: Literal["buy", "sell"]
    quantity: int
    trade_date: str
    settlement_date: str
    event_time: datetime
    reference_price: float
    fill_price: float
    slippage: float
    commission: float
    transfer_fee: float
    tax: float
    total_cost: float
    assumption_hash: str
    market_snapshot_hash: str
    market_lineage_hash: str


class PaperExecutionReceiptResponse(BaseModel):
    """Created or replayed execution with compact inspector evidence."""

    model_config = _RESPONSE_CONFIG

    status: Literal["created", "replayed"]
    execution_id: str
    idempotency_key: str
    request_hash: str
    order_id: str
    order_status: str
    reality_status: str
    reason: str | None
    fill: PaperFillResponse | None
    ledger_event_id: str | None

    @classmethod
    def from_info(
        cls,
        *,
        status: Literal["created", "replayed"],
        info: PaperExecutionInfo,
    ) -> Self:
        """Project a durable execution into the stable HTTP read model."""
        return cls(
            status=status,
            execution_id=info.execution_id,
            idempotency_key=info.idempotency_key,
            request_hash=info.request_hash,
            order_id=info.order_id,
            order_status=info.order_status,
            reality_status=info.reality_status,
            reason=info.reason,
            fill=(
                PaperFillResponse.model_validate(info.fill)
                if info.fill is not None
                else None
            ),
            ledger_event_id=info.ledger_event_id,
        )


class PaperReconciliationResponse(BaseModel):
    """End-of-day fill-to-ledger checksum."""

    model_config = _RESPONSE_CONFIG

    reconciliation_id: str
    session_id: str
    trade_date: str
    order_count: int
    fill_count: int
    ledger_fill_count: int
    balanced: bool
    checksum: str
    reconciled_at: datetime


class PaperSessionReadResponse(BaseModel):
    """Session, execution inspector rows, and latest reconciliation."""

    model_config = _RESPONSE_CONFIG

    session: PaperSessionResponse
    executions: tuple[PaperExecutionReceiptResponse, ...]
    latest_reconciliation: PaperReconciliationResponse | None


class PaperRecoverResponse(BaseModel):
    """Recovery entrypoint result."""

    model_config = _RESPONSE_CONFIG

    idempotency_key: str
    recovered_execution_count: int
