"""Version-compatible deterministic runtime snapshots for backtest resume."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from typing import cast

import orjson
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.trade_builder import TradeBuilderStateSnapshot
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.context import StrategyContextSnapshot

from ditto_backtest._checkpoint_codec import (
    finite_float,
    optional_finite_float,
    payload_float,
    payload_int,
    payload_mapping,
    payload_optional_float,
    payload_optional_int,
    payload_optional_str,
    payload_sequence,
    payload_str,
    require_exact_keys,
)
from ditto_backtest._trade_builder_checkpoint import (
    trade_builder_from_payload,
    trade_builder_to_payload,
)
from ditto_backtest.audit.state import ExecutionAuditStateSnapshot

__all__ = [
    "BacktestDelayedSignalSnapshot",
    "BacktestPendingOrderSnapshot",
    "BacktestRiskLockSnapshot",
    "BacktestRuntimeStateCapture",
    "BacktestRuntimeStateSnapshot",
    "BacktestStrategyContextSnapshot",
    "BacktestStrategyCostSnapshot",
    "BacktestTargetWeightSnapshot",
]

_EXACT_RUNTIME_STATE_VERSION = 2


@dataclass(frozen=True)
class BacktestPendingOrderSnapshot:
    """Checkpoint-safe pending order ticket snapshot."""

    client_order_id: str
    instrument_id: InstrumentId
    order_type: str
    direction: str
    quantity: int
    price: float | None
    stop_price: float | None
    trade_date: str | None
    status: str
    filled_quantity: int
    leaves_quantity: int
    filled_price: float | None
    average_fill_price: float | None

    @classmethod
    def from_ticket(cls, ticket: OrderTicket) -> BacktestPendingOrderSnapshot:
        """Convert an execution ticket into deterministic checkpoint data."""
        order = ticket.order
        return cls(
            client_order_id=order.client_id.value,
            instrument_id=order.instrument_id,
            order_type=order.order_type.value,
            direction=order.direction.value,
            quantity=order.quantity,
            price=order.price,
            stop_price=order.stop_price,
            trade_date=order.trade_date,
            status=ticket.status.value,
            filled_quantity=ticket.filled_quantity,
            leaves_quantity=ticket.leaves_quantity,
            filled_price=ticket.filled_price,
            average_fill_price=ticket.average_fill_price,
        )

    def to_payload(self) -> dict[str, int | float | str | None]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "average_fill_price": optional_finite_float(
                self.average_fill_price,
                "average_fill_price",
            ),
            "client_order_id": self.client_order_id,
            "direction": self.direction,
            "filled_price": optional_finite_float(self.filled_price, "filled_price"),
            "filled_quantity": self.filled_quantity,
            "instrument_id": int(self.instrument_id),
            "leaves_quantity": self.leaves_quantity,
            "order_type": self.order_type,
            "price": optional_finite_float(self.price, "price"),
            "quantity": self.quantity,
            "status": self.status,
            "stop_price": optional_finite_float(self.stop_price, "stop_price"),
            "trade_date": self.trade_date,
        }

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        strict: bool = False,
    ) -> BacktestPendingOrderSnapshot:
        """Deserialize a pending-order checkpoint payload."""
        data = payload_mapping(payload)
        if strict:
            require_exact_keys(
                data,
                (
                    "average_fill_price",
                    "client_order_id",
                    "direction",
                    "filled_price",
                    "filled_quantity",
                    "instrument_id",
                    "leaves_quantity",
                    "order_type",
                    "price",
                    "quantity",
                    "status",
                    "stop_price",
                    "trade_date",
                ),
            )
        return cls(
            client_order_id=payload_str(data, "client_order_id"),
            instrument_id=InstrumentId(payload_int(data, "instrument_id")),
            order_type=payload_str(data, "order_type"),
            direction=payload_str(data, "direction"),
            quantity=payload_int(data, "quantity"),
            price=payload_optional_float(data, "price"),
            stop_price=payload_optional_float(data, "stop_price"),
            trade_date=payload_optional_str(data, "trade_date"),
            status=payload_str(data, "status"),
            filled_quantity=payload_int(data, "filled_quantity"),
            leaves_quantity=payload_int(data, "leaves_quantity"),
            filled_price=payload_optional_float(data, "filled_price"),
            average_fill_price=payload_optional_float(data, "average_fill_price"),
        )


@dataclass(frozen=True)
class BacktestTargetWeightSnapshot:
    """Checkpoint-safe target weight snapshot for a delayed signal."""

    instrument_id: InstrumentId
    target_weight: float

    def __post_init__(self) -> None:
        """Reject non-finite target weights at the DTO boundary."""
        finite_float(self.target_weight, "target_weight")

    def to_payload(self) -> dict[str, int | float]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "instrument_id": int(self.instrument_id),
            "target_weight": finite_float(self.target_weight, "target_weight"),
        }

    @classmethod
    def from_payload(
        cls, payload: object, *, strict: bool = False
    ) -> BacktestTargetWeightSnapshot:
        """Deserialize a delayed-signal target-weight payload."""
        data = payload_mapping(payload)
        if strict:
            require_exact_keys(data, ("instrument_id", "target_weight"))
        return cls(
            instrument_id=InstrumentId(payload_int(data, "instrument_id")),
            target_weight=payload_float(data, "target_weight"),
        )


@dataclass(frozen=True)
class BacktestDelayedSignalSnapshot:
    """Checkpoint-safe delayed target-portfolio signal snapshot."""

    queue_index: int
    trade_date: str
    strategy_id: str
    run_id: str
    cash_target: float
    positions: tuple[BacktestTargetWeightSnapshot, ...] = ()

    def __post_init__(self) -> None:
        """Validate ordering identity and all delayed signal values."""
        if type(self.queue_index) is not int or self.queue_index < 0:
            raise ValueError("checkpoint delayed queue index must be non-negative")
        _require_iso_date("trade_date", self.trade_date)
        finite_float(self.cash_target, "cash_target")
        _require_unique_instruments(
            "delayed_signal.positions",
            tuple(item.instrument_id for item in self.positions),
        )

    @classmethod
    def from_signal(
        cls,
        queue_index: int,
        signal: object,
    ) -> BacktestDelayedSignalSnapshot:
        """Convert TargetPortfolio-like signal into deterministic data."""
        return cls(
            queue_index=queue_index,
            trade_date=str(getattr(signal, "trade_date", "")),
            strategy_id=str(getattr(signal, "strategy_id", "")),
            run_id=str(getattr(signal, "run_id", "")),
            cash_target=float(getattr(signal, "cash_target", 0.0)),
            positions=_snapshot_target_weights(getattr(signal, "positions", {})),
        )

    def to_payload(self) -> dict[str, object]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "cash_target": finite_float(self.cash_target, "cash_target"),
            "positions": [position.to_payload() for position in self.positions],
            "queue_index": self.queue_index,
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "trade_date": self.trade_date,
        }

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        strict: bool = False,
    ) -> BacktestDelayedSignalSnapshot:
        """Deserialize a delayed-signal checkpoint payload."""
        data = payload_mapping(payload)
        if strict:
            require_exact_keys(
                data,
                (
                    "cash_target",
                    "positions",
                    "queue_index",
                    "run_id",
                    "strategy_id",
                    "trade_date",
                ),
            )
        return cls(
            queue_index=payload_int(data, "queue_index"),
            trade_date=payload_str(data, "trade_date"),
            strategy_id=payload_str(data, "strategy_id"),
            run_id=payload_str(data, "run_id"),
            cash_target=payload_float(data, "cash_target"),
            positions=tuple(
                BacktestTargetWeightSnapshot.from_payload(position, strict=strict)
                for position in payload_sequence(data, "positions")
            ),
        )


@dataclass(frozen=True)
class BacktestRiskLockSnapshot:
    """One deterministic StrategyContext risk lock."""

    instrument_id: InstrumentId
    reason: str
    cooldown_until: str | None

    def __post_init__(self) -> None:
        """Validate optional cooldown dates before they enter evidence JSON."""
        if self.cooldown_until is not None:
            _require_iso_date("cooldown_until", self.cooldown_until)

    def to_payload(self) -> dict[str, int | str | None]:
        """Return stable JSON data for one risk lock."""
        return {
            "cooldown_until": self.cooldown_until,
            "instrument_id": int(self.instrument_id),
            "reason": self.reason,
        }

    @classmethod
    def from_payload(
        cls, payload: object, *, strict: bool = False
    ) -> BacktestRiskLockSnapshot:
        """Deserialize one risk lock."""
        data = payload_mapping(payload)
        if strict:
            require_exact_keys(data, ("cooldown_until", "instrument_id", "reason"))
        return cls(
            instrument_id=InstrumentId(payload_int(data, "instrument_id")),
            reason=payload_str(data, "reason"),
            cooldown_until=payload_optional_str(data, "cooldown_until"),
        )


@dataclass(frozen=True)
class BacktestStrategyCostSnapshot:
    """One deterministic StrategyContext average-cost entry."""

    instrument_id: InstrumentId
    average_cost: float

    def __post_init__(self) -> None:
        """Reject non-finite average costs at the DTO boundary."""
        finite_float(self.average_cost, "average_cost")

    def to_payload(self) -> dict[str, int | float]:
        """Return stable JSON data for one strategy cost entry."""
        return {
            "average_cost": finite_float(self.average_cost, "average_cost"),
            "instrument_id": int(self.instrument_id),
        }

    @classmethod
    def from_payload(
        cls, payload: object, *, strict: bool = False
    ) -> BacktestStrategyCostSnapshot:
        """Deserialize one strategy cost entry."""
        data = payload_mapping(payload)
        if strict:
            require_exact_keys(data, ("average_cost", "instrument_id"))
        return cls(
            instrument_id=InstrumentId(payload_int(data, "instrument_id")),
            average_cost=payload_float(data, "average_cost"),
        )


@dataclass(frozen=True)
class BacktestStrategyContextSnapshot:
    """Immutable JSON-safe projection of StrategyContextSnapshot."""

    risk_locks: tuple[BacktestRiskLockSnapshot, ...] = ()
    position_costs: tuple[BacktestStrategyCostSnapshot, ...] = ()

    def __post_init__(self) -> None:
        """Reject duplicate instrument keys that would collapse on restore."""
        _require_unique_instruments(
            "risk_locks",
            tuple(item.instrument_id for item in self.risk_locks),
        )
        _require_unique_instruments(
            "position_costs",
            tuple(item.instrument_id for item in self.position_costs),
        )

    @classmethod
    def from_strategy_snapshot(
        cls,
        snapshot: StrategyContextSnapshot | None,
    ) -> BacktestStrategyContextSnapshot:
        """Build deterministic tuples from the strategy-owned snapshot DTO."""
        if snapshot is None:
            return cls()
        return cls(
            risk_locks=tuple(
                BacktestRiskLockSnapshot(iid, reason, cooldown)
                for iid, (reason, cooldown) in snapshot.risk_locked_instruments.items()
            ),
            position_costs=tuple(
                BacktestStrategyCostSnapshot(iid, cost)
                for iid, cost in snapshot.positions.items()
            ),
        )

    def to_strategy_snapshot(self) -> StrategyContextSnapshot:
        """Restore the strategy-owned snapshot DTO."""
        return StrategyContextSnapshot(
            risk_locked_instruments={
                lock.instrument_id: (lock.reason, lock.cooldown_until)
                for lock in self.risk_locks
            },
            positions={
                position.instrument_id: position.average_cost
                for position in self.position_costs
            },
        )

    def to_payload(self) -> dict[str, object]:
        """Return stable JSON data for strategy context state."""
        return {
            "position_costs": [item.to_payload() for item in self.position_costs],
            "risk_locks": [item.to_payload() for item in self.risk_locks],
        }

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        strict: bool = False,
    ) -> BacktestStrategyContextSnapshot:
        """Deserialize strategy context state."""
        data = payload_mapping(payload)
        if strict:
            require_exact_keys(data, ("position_costs", "risk_locks"))
        return cls(
            risk_locks=tuple(
                BacktestRiskLockSnapshot.from_payload(item, strict=strict)
                for item in payload_sequence(data, "risk_locks")
            ),
            position_costs=tuple(
                BacktestStrategyCostSnapshot.from_payload(item, strict=strict)
                for item in payload_sequence(data, "position_costs")
            ),
        )


@dataclass(frozen=True)
class BacktestRuntimeStateCapture:
    """Typed live inputs for one runtime-state checkpoint projection."""

    pending_tickets: tuple[OrderTicket, ...] = ()
    delayed_signals: tuple[object, ...] = ()
    strategy_context: StrategyContextSnapshot | None = None
    planner_id_counter: int = 0
    brokerage_fill_counter: int = 0
    trade_builder_state: TradeBuilderStateSnapshot | None = None
    rebalance_calendar_start: str | None = None
    audit_state_json: str | None = None
    attest_exact: bool = True


@dataclass(frozen=True)
class BacktestRuntimeStateSnapshot:
    """Checkpoint-safe, version-compatible engine runtime state."""

    pending_orders: tuple[BacktestPendingOrderSnapshot, ...] = ()
    delayed_signals: tuple[BacktestDelayedSignalSnapshot, ...] = ()
    strategy_context: BacktestStrategyContextSnapshot = field(
        default_factory=BacktestStrategyContextSnapshot,
    )
    planner_id_counter: int = 0
    brokerage_fill_counter: int = 0
    trade_builder_state: TradeBuilderStateSnapshot | None = None
    rebalance_calendar_start: str | None = None
    audit_state_json: str | None = None
    runtime_state_version: int | None = None

    def __post_init__(self) -> None:
        """Reject invalid persisted counter values at the DTO boundary."""
        _require_non_negative_counter("planner_id_counter", self.planner_id_counter)
        _require_non_negative_counter(
            "brokerage_fill_counter",
            self.brokerage_fill_counter,
        )
        if self.runtime_state_version not in (None, _EXACT_RUNTIME_STATE_VERSION):
            msg = "checkpoint runtime state version is unsupported"
            raise ValueError(msg)
        if self.rebalance_calendar_start is not None:
            _require_iso_date(
                "rebalance_calendar_start",
                self.rebalance_calendar_start,
            )
        if self.audit_state_json is not None and (
            type(self.audit_state_json) is not str or not self.audit_state_json
        ):
            msg = "checkpoint audit_state_json must be a non-empty string"
            raise ValueError(msg)
        queue_indices = tuple(item.queue_index for item in self.delayed_signals)
        if queue_indices != tuple(range(len(queue_indices))):
            msg = "checkpoint delayed signal queue indices must be contiguous"
            raise ValueError(msg)

    @classmethod
    def from_state(
        cls,
        capture: BacktestRuntimeStateCapture | None = None,
    ) -> BacktestRuntimeStateSnapshot:
        """Convert all result-determining runtime state into checkpoint data."""
        state = capture or BacktestRuntimeStateCapture()
        return cls(
            pending_orders=_snapshot_pending_orders(state.pending_tickets),
            delayed_signals=tuple(
                BacktestDelayedSignalSnapshot.from_signal(index, signal)
                for index, signal in enumerate(state.delayed_signals)
            ),
            strategy_context=(
                BacktestStrategyContextSnapshot.from_strategy_snapshot(
                    state.strategy_context,
                )
            ),
            planner_id_counter=state.planner_id_counter,
            brokerage_fill_counter=state.brokerage_fill_counter,
            trade_builder_state=state.trade_builder_state,
            rebalance_calendar_start=state.rebalance_calendar_start,
            audit_state_json=state.audit_state_json,
            runtime_state_version=(
                _EXACT_RUNTIME_STATE_VERSION
                if state.attest_exact
                and state.trade_builder_state is not None
                and state.rebalance_calendar_start is not None
                and state.audit_state_json is not None
                else None
            ),
        )

    @property
    def is_exact_resume_state(self) -> bool:
        """Whether the producer attested every state owner required by V2."""
        return (
            self.runtime_state_version == _EXACT_RUNTIME_STATE_VERSION
            and self.trade_builder_state is not None
            and self.rebalance_calendar_start is not None
            and self.audit_state_json is not None
            and _is_canonical_audit_state_json(self.audit_state_json)
            and self.planner_id_counter >= _pending_order_counter(self.pending_orders)
        )

    @property
    def resolved_planner_id_counter(self) -> int:
        """Include legacy pending client IDs when no explicit counter existed."""
        return max(self.planner_id_counter, _pending_order_counter(self.pending_orders))

    def to_strategy_context_snapshot(self) -> StrategyContextSnapshot:
        """Project the immutable JSON-safe state back to the strategy DTO."""
        return self.strategy_context.to_strategy_snapshot()

    def to_payload(self) -> dict[str, object]:
        """Return full V2 JSON or omission-compatible legacy JSON."""
        payload: dict[str, object] = {
            "delayed_signals": [signal.to_payload() for signal in self.delayed_signals],
            "pending_orders": [order.to_payload() for order in self.pending_orders],
        }
        if self.runtime_state_version is not None:
            if not self.is_exact_resume_state:
                msg = "versioned checkpoint runtime state is incomplete"
                raise ValueError(msg)
            payload.update(
                {
                    "audit_state_json": self.audit_state_json,
                    "brokerage_fill_counter": self.brokerage_fill_counter,
                    "planner_id_counter": self.planner_id_counter,
                    "rebalance_calendar_start": self.rebalance_calendar_start,
                    "runtime_state_version": self.runtime_state_version,
                    "strategy_context": self.strategy_context.to_payload(),
                }
            )
            if self.trade_builder_state is None:
                raise ValueError("versioned checkpoint trade-builder state is missing")
            payload["trade_builder_state"] = trade_builder_to_payload(
                self.trade_builder_state,
            )
            return payload
        if self.rebalance_calendar_start is not None:
            payload["rebalance_calendar_start"] = self.rebalance_calendar_start
        if self.audit_state_json is not None:
            payload["audit_state_json"] = self.audit_state_json
        if self.strategy_context != BacktestStrategyContextSnapshot():
            payload["strategy_context"] = self.strategy_context.to_payload()
        if self.planner_id_counter:
            payload["planner_id_counter"] = self.planner_id_counter
        if self.brokerage_fill_counter:
            payload["brokerage_fill_counter"] = self.brokerage_fill_counter
        if self.trade_builder_state is not None:
            payload["trade_builder_state"] = trade_builder_to_payload(
                self.trade_builder_state,
            )
        return payload

    def to_json(self) -> str:
        """Serialize the runtime state with deterministic key ordering."""
        return orjson.dumps(self.to_payload(), option=orjson.OPT_SORT_KEYS).decode()

    @property
    def state_hash(self) -> str:
        """Stable content hash for replay/resume evidence."""
        digest = sha256(self.to_json().encode()).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_payload(cls, payload: object) -> BacktestRuntimeStateSnapshot:
        """Deserialize both v1 and extended deterministic runtime payloads."""
        data = payload_mapping(payload)
        context_payload = data.get("strategy_context")
        trade_builder_payload = data.get("trade_builder_state")
        version_payload = data.get("runtime_state_version")
        if version_payload is not None and type(version_payload) is not int:
            msg = "checkpoint field 'runtime_state_version' must be an integer"
            raise ValueError(msg)
        is_v2 = version_payload == _EXACT_RUNTIME_STATE_VERSION
        if is_v2:
            require_exact_keys(
                data,
                (
                    "audit_state_json",
                    "brokerage_fill_counter",
                    "delayed_signals",
                    "pending_orders",
                    "planner_id_counter",
                    "rebalance_calendar_start",
                    "runtime_state_version",
                    "strategy_context",
                    "trade_builder_state",
                ),
            )
            require_exact_keys(
                payload_mapping(context_payload),
                ("position_costs", "risk_locks"),
            )
        if is_v2:
            audit_state_json = payload_str(data, "audit_state_json")
            _require_canonical_audit_state_json(audit_state_json)
        else:
            audit_state_json = payload_optional_str(data, "audit_state_json")
        return cls(
            pending_orders=tuple(
                BacktestPendingOrderSnapshot.from_payload(order, strict=is_v2)
                for order in payload_sequence(data, "pending_orders")
            ),
            delayed_signals=tuple(
                BacktestDelayedSignalSnapshot.from_payload(signal, strict=is_v2)
                for signal in payload_sequence(data, "delayed_signals")
            ),
            strategy_context=(
                BacktestStrategyContextSnapshot()
                if context_payload is None
                else BacktestStrategyContextSnapshot.from_payload(
                    context_payload,
                    strict=is_v2,
                )
            ),
            planner_id_counter=(
                payload_int(data, "planner_id_counter")
                if is_v2
                else payload_optional_int(data, "planner_id_counter")
            ),
            brokerage_fill_counter=(
                payload_int(data, "brokerage_fill_counter")
                if is_v2
                else payload_optional_int(data, "brokerage_fill_counter")
            ),
            trade_builder_state=(
                None
                if trade_builder_payload is None
                else trade_builder_from_payload(
                    trade_builder_payload,
                    strict=is_v2,
                )
            ),
            rebalance_calendar_start=payload_optional_str(
                data,
                "rebalance_calendar_start",
            ),
            audit_state_json=audit_state_json,
            runtime_state_version=version_payload,
        )

    @classmethod
    def from_json(cls, payload_json: str) -> BacktestRuntimeStateSnapshot:
        """Deserialize deterministic runtime-state JSON."""
        return cls.from_payload(cast(object, orjson.loads(payload_json)))


def _snapshot_pending_orders(
    pending_tickets: tuple[OrderTicket, ...],
) -> tuple[BacktestPendingOrderSnapshot, ...]:
    """Preserve OrderBook iteration order because execution is order-sensitive."""
    return tuple(
        BacktestPendingOrderSnapshot.from_ticket(ticket) for ticket in pending_tickets
    )


def _snapshot_target_weights(
    positions: object,
) -> tuple[BacktestTargetWeightSnapshot, ...]:
    if not isinstance(positions, Mapping):
        return ()
    typed_positions = cast(Mapping[object, object], positions)
    snapshots = [
        BacktestTargetWeightSnapshot(
            instrument_id=InstrumentId(int(instrument_id)),
            target_weight=float(target_weight),
        )
        for instrument_id, target_weight in typed_positions.items()
        if isinstance(instrument_id, int | str)
        and not isinstance(target_weight, bool)
        and isinstance(target_weight, int | float)
    ]
    return tuple(snapshots)


def _pending_order_counter(orders: tuple[BacktestPendingOrderSnapshot, ...]) -> int:
    highest = 0
    for order in orders:
        prefix, separator, suffix = order.client_order_id.rpartition("-")
        if prefix == "plan-order" and separator and suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest


def _require_non_negative_counter(name: str, counter: int) -> None:
    if type(counter) is not int or counter < 0:
        msg = f"checkpoint field {name!r} must be a non-negative integer"
        raise ValueError(msg)


def _require_iso_date(name: str, value: str) -> None:
    if not value:
        msg = f"checkpoint field {name!r} must be a non-empty ISO date"
        raise ValueError(msg)
    try:
        date.fromisoformat(value)
    except ValueError:
        msg = f"checkpoint field {name!r} must be an ISO date"
        raise ValueError(msg) from None


def _require_unique_instruments(
    name: str,
    instrument_ids: tuple[InstrumentId, ...],
) -> None:
    if len(set(instrument_ids)) != len(instrument_ids):
        msg = f"checkpoint field {name!r} contains duplicate instruments"
        raise ValueError(msg)


def _is_canonical_audit_state_json(payload_json: str) -> bool:
    try:
        _require_canonical_audit_state_json(payload_json)
    except (TypeError, ValueError):
        return False
    return True


def _require_canonical_audit_state_json(payload_json: str) -> None:
    """Typed-decode the complete audit tree before accepting V2 evidence."""
    ExecutionAuditStateSnapshot.from_canonical_json(payload_json)
