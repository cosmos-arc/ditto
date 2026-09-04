"""Immutable paper order, fill-assumption, and market-lineage contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_kernel.trading import MarketSnapshot

from ditto_execution.errors import OrderStateError
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.fsm import transition
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger

__all__ = [
    "FillAssumption",
    "MarketSnapshotLineage",
    "PaperFill",
    "PaperOrder",
    "PaperRealityContext",
    "PaperRealityResult",
    "PaperRealityStatus",
]


def _canonical_hash(prefix: str, payload: dict[str, object]) -> str:
    encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return f"{prefix}:sha256:{sha256(encoded).hexdigest()}"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, kw_only=True)
class FillAssumption:
    """Versioned pricing policy used to derive one simulated fill."""

    assumption_id: str
    version: int
    reference_price_field: str
    slippage_bps: float
    assumption_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate policy fields and derive its canonical identity."""
        if not self.assumption_id.strip():
            raise ValueError("assumption_id must be non-empty")
        if self.version <= 0:
            raise ValueError("assumption version must be positive")
        if self.reference_price_field not in {"open", "close"}:
            raise ValueError("reference_price_field must be open or close")
        if not isfinite(self.slippage_bps) or self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative and finite")
        object.__setattr__(
            self,
            "assumption_hash",
            _canonical_hash(
                "fill-assumption",
                {
                    "assumption_id": self.assumption_id,
                    "version": self.version,
                    "reference_price_field": self.reference_price_field,
                    "slippage_bps": self.slippage_bps,
                },
            ),
        )


@dataclass(frozen=True, kw_only=True)
class MarketSnapshotLineage:
    """Exact market payload plus source and publication visibility evidence."""

    snapshot: MarketSnapshot
    dataset_id: str
    source: str
    source_snapshot_id: str
    observed_at: datetime
    publication_cutoff: datetime
    snapshot_hash: str
    lineage_hash: str

    @classmethod
    def create(
        cls,
        *,
        snapshot: MarketSnapshot,
        dataset_id: str,
        source: str,
        source_snapshot_id: str,
        observed_at: datetime,
        publication_cutoff: datetime,
    ) -> MarketSnapshotLineage:
        """Build canonical payload and lineage hashes from explicit provenance."""
        _require_aware(observed_at, "observed_at")
        _require_aware(publication_cutoff, "publication_cutoff")
        for name, value in (
            ("dataset_id", dataset_id),
            ("source", source),
            ("source_snapshot_id", source_snapshot_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        snapshot_payload: dict[str, object] = {
            "trade_date": snapshot.trade_date,
            "instrument_id": int(snapshot.instrument_id),
            "open": snapshot.open,
            "high": snapshot.high,
            "low": snapshot.low,
            "close": snapshot.close,
            "prev_close": snapshot.prev_close,
            "volume": snapshot.volume,
            "amount": snapshot.amount,
            "is_suspended": snapshot.is_suspended,
            "limit_up": snapshot.limit_up,
            "limit_down": snapshot.limit_down,
            "avg_volume_20d": snapshot.avg_volume_20d,
        }
        snapshot_hash = _canonical_hash("market-snapshot", snapshot_payload)
        lineage_hash = _canonical_hash(
            "market-lineage",
            {
                "dataset_id": dataset_id,
                "source": source,
                "source_snapshot_id": source_snapshot_id,
                "observed_at": observed_at.isoformat(),
                "publication_cutoff": publication_cutoff.isoformat(),
                "snapshot_hash": snapshot_hash,
            },
        )
        return cls(
            snapshot=snapshot,
            dataset_id=dataset_id,
            source=source,
            source_snapshot_id=source_snapshot_id,
            observed_at=observed_at,
            publication_cutoff=publication_cutoff,
            snapshot_hash=snapshot_hash,
            lineage_hash=lineage_hash,
        )

    def assert_visible_at(self, execution_at: datetime) -> None:
        """Fail closed when execution consumes a not-yet-visible snapshot."""
        _require_aware(execution_at, "execution_at")
        if self.observed_at > execution_at:
            raise ValueError("market snapshot observed_at is after execution_at")
        if self.publication_cutoff > execution_at:
            raise ValueError("market snapshot publication_cutoff is after execution_at")


@dataclass(frozen=True, kw_only=True)
class PaperFill:
    """One immutable simulated fill with complete economic and lineage evidence."""

    fill_id: str
    session_id: str
    account_id: str
    order_id: str
    instrument_id: InstrumentId
    direction: OrderSide
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

    def __post_init__(self) -> None:
        """Validate immutable fill economics."""
        _require_aware(self.event_time, "event_time")
        if self.quantity <= 0:
            raise ValueError("paper fill quantity must be positive")
        if not isfinite(self.fill_price) or self.fill_price <= 0:
            raise ValueError("paper fill price must be positive and finite")


@dataclass(frozen=True, kw_only=True)
class PaperOrder:
    """Paper identity around the shared, audited ``OrderTicket`` FSM."""

    session_id: str
    account_id: str
    idempotency_key: str
    submitted_at: datetime
    ticket: OrderTicket

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        account_id: str,
        idempotency_key: str,
        order: Order,
        submitted_at: datetime,
    ) -> PaperOrder:
        """Create a NEW paper order without bypassing the shared FSM."""
        _require_aware(submitted_at, "submitted_at")
        for name, value in (
            ("session_id", session_id),
            ("account_id", account_id),
            ("idempotency_key", idempotency_key),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if order.quantity <= 0:
            raise ValueError("order quantity must be positive")
        return cls(
            session_id=session_id,
            account_id=account_id,
            idempotency_key=idempotency_key,
            submitted_at=submitted_at,
            ticket=OrderTicket(order=order),
        )

    @property
    def order(self) -> Order:
        """Return the shared execution order."""
        return self.ticket.order

    @property
    def order_id(self) -> str:
        """Return the shared client-order identity."""
        return self.ticket.order.order_id

    @property
    def status(self) -> OrderStatus:
        """Return the current shared FSM state."""
        return self.ticket.status

    def submit(self) -> PaperOrder:
        """Return a submitted copy and record the transition event."""
        status = transition(self.status, OrderTrigger.SUBMIT)
        event = OrderEvent(
            client_id=self.order.client_id,
            trigger=OrderTrigger.SUBMIT,
            status=status,
            timestamp=self.submitted_at,
        )
        return replace(
            self,
            ticket=replace(
                self.ticket,
                status=status,
                order_events=(*self.ticket.order_events, event),
            ),
        )

    def record_fill(self, fill: PaperFill) -> PaperOrder:
        """Apply one matching fill through the shared order FSM."""
        if self.status.is_terminal:
            raise OrderStateError(
                f"Cannot fill terminal paper order: {self.status.value}"
            )
        if (
            fill.order_id != self.order_id
            or fill.session_id != self.session_id
            or fill.account_id != self.account_id
            or fill.instrument_id != self.order.instrument_id
            or fill.direction is not self.order.direction
        ):
            raise OrderStateError("paper fill identity does not match order")
        expected_status = (
            OrderStatus.FILLED
            if fill.quantity == self.ticket.leaves_quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        event = OrderEvent(
            client_id=self.order.client_id,
            trigger=OrderTrigger.FILL,
            status=expected_status,
            fill_price=fill.fill_price,
            fill_quantity=fill.quantity,
            fee=fill.total_cost,
            timestamp=fill.event_time,
        )
        return replace(
            self,
            ticket=self.ticket.with_fill(
                quantity=fill.quantity,
                price=fill.fill_price,
                event=event,
            ),
        )

    def reject(self, *, reason: str, timestamp: datetime) -> PaperOrder:
        """Reject a submitted order with a durable reason."""
        event = OrderEvent(
            client_id=self.order.client_id,
            trigger=OrderTrigger.REJECT,
            status=OrderStatus.REJECTED,
            message=reason,
            timestamp=timestamp,
        )
        return replace(self, ticket=self.ticket.with_reject(event))


class PaperRealityStatus(StrEnum):
    """Outcome class for one deterministic paper execution attempt."""

    FILLED = "filled"
    DEFERRED = "deferred"
    REJECTED = "rejected"


@dataclass(frozen=True, kw_only=True)
class PaperRealityContext:
    """Separate order-decision and simulated-execution time inputs."""

    decision_at: datetime
    execution_at: datetime
    settlement_date: str
    position_quantity: int
    available_quantity: int

    def __post_init__(self) -> None:
        """Reject ambiguous or causally reversed execution timing."""
        _require_aware(self.decision_at, "decision_at")
        _require_aware(self.execution_at, "execution_at")
        if self.execution_at < self.decision_at:
            raise ValueError("execution_at cannot precede decision_at")


@dataclass(frozen=True, kw_only=True)
class PaperRealityResult:
    """Explicit paper reality result; no ``None`` side channel."""

    status: PaperRealityStatus
    order: PaperOrder
    reason: str | None = None
    fill: PaperFill | None = None
