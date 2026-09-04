"""
Application-owned PAPER inputs and primitive read models.

These contracts keep HTTP and other entrypoints from importing execution-owned
domain records while preserving the exact hashes and state recorded by the
Paper runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_execution.paper.session import (
    PaperExecutionRecord,
    PaperReconciliation,
    PaperSession,
)

__all__ = [
    "PaperExecutionInfo",
    "PaperFillAssumptionInput",
    "PaperFillInfo",
    "PaperInstrumentRulesInput",
    "PaperMarketSnapshotInput",
    "PaperReconciliationInfo",
    "PaperSessionInfo",
    "to_paper_execution_info",
    "to_paper_reconciliation_info",
    "to_paper_session_info",
]


@dataclass(frozen=True, kw_only=True)
class PaperMarketSnapshotInput:
    """Market payload and explicit point-in-time provenance."""

    dataset_id: str
    source: str
    source_snapshot_id: str
    observed_at: datetime
    publication_cutoff: datetime
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: float
    amount: float
    is_suspended: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    avg_volume_20d: float | None = None


@dataclass(frozen=True, kw_only=True)
class PaperInstrumentRulesInput:
    """Static instrument, trading-rule, and fee inputs for one operation."""

    asset_class: str
    exchange: str
    tick_size: float
    lot_size: int
    board_segment: str
    settlement_cycle: int
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    currency: str = "CNY"
    multiplier: float = 1.0
    lifecycle_state: str = "listed"
    price_limit_pct: float | None = 0.1


@dataclass(frozen=True, kw_only=True)
class PaperFillAssumptionInput:
    """Versioned simulated-fill policy input."""

    assumption_id: str
    version: int
    reference_price_field: str
    slippage_bps: float


@dataclass(frozen=True, kw_only=True)
class PaperSessionInfo:
    """Application projection of durable Paper session state."""

    session_id: str
    account_id: str
    strategy_id: str
    trade_date: str
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime
    pause_reason: str | None


@dataclass(frozen=True, kw_only=True)
class PaperFillInfo:
    """Application projection of simulated fill economics and lineage."""

    fill_id: str
    order_id: str
    instrument_id: int
    direction: str
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


@dataclass(frozen=True, kw_only=True)
class PaperExecutionInfo:
    """Application projection of one persisted Paper execution."""

    execution_id: str
    idempotency_key: str
    request_hash: str
    order_id: str
    order_status: str
    reality_status: str
    reason: str | None
    fill: PaperFillInfo | None
    ledger_event_id: str | None


@dataclass(frozen=True, kw_only=True)
class PaperReconciliationInfo:
    """Application projection of an end-of-day reconciliation artifact."""

    reconciliation_id: str
    session_id: str
    trade_date: str
    order_count: int
    fill_count: int
    ledger_fill_count: int
    balanced: bool
    checksum: str
    reconciled_at: datetime


def to_paper_session_info(session: PaperSession) -> PaperSessionInfo:
    """Project an execution-owned session without leaking its enum type."""
    return PaperSessionInfo(
        session_id=session.session_id,
        account_id=session.account_id,
        strategy_id=session.strategy_id,
        trade_date=session.trade_date,
        status=session.status.value,
        revision=session.revision,
        created_at=session.created_at,
        updated_at=session.updated_at,
        pause_reason=session.pause_reason,
    )


def to_paper_execution_info(record: PaperExecutionRecord) -> PaperExecutionInfo:
    """Project a durable execution with exact fill evidence."""
    fill = record.result.fill
    fill_info = (
        PaperFillInfo(
            fill_id=fill.fill_id,
            order_id=fill.order_id,
            instrument_id=int(fill.instrument_id),
            direction=fill.direction.value,
            quantity=fill.quantity,
            trade_date=fill.trade_date,
            settlement_date=fill.settlement_date,
            event_time=fill.event_time,
            reference_price=fill.reference_price,
            fill_price=fill.fill_price,
            slippage=fill.slippage,
            commission=fill.commission,
            transfer_fee=fill.transfer_fee,
            tax=fill.tax,
            total_cost=fill.total_cost,
            assumption_hash=fill.assumption_hash,
            market_snapshot_hash=fill.market_snapshot_hash,
            market_lineage_hash=fill.market_lineage_hash,
        )
        if fill is not None
        else None
    )
    return PaperExecutionInfo(
        execution_id=record.execution_id,
        idempotency_key=record.idempotency_key,
        request_hash=record.request_hash,
        order_id=record.result.order.order_id,
        order_status=record.result.order.status.value,
        reality_status=record.result.status.value,
        reason=record.result.reason,
        fill=fill_info,
        ledger_event_id=record.ledger_event_id,
    )


def to_paper_reconciliation_info(
    reconciliation: PaperReconciliation,
) -> PaperReconciliationInfo:
    """Project one stored reconciliation into the application boundary."""
    return PaperReconciliationInfo(
        reconciliation_id=reconciliation.reconciliation_id,
        session_id=reconciliation.session_id,
        trade_date=reconciliation.trade_date,
        order_count=reconciliation.order_count,
        fill_count=reconciliation.fill_count,
        ledger_fill_count=reconciliation.ledger_fill_count,
        balanced=reconciliation.balanced,
        checksum=reconciliation.checksum,
        reconciled_at=reconciliation.reconciled_at,
    )
