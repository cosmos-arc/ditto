"""Backtest engine result model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from typing import cast

import orjson
from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting import AccountView, FillEvent
from ditto_portfolio.accounting.position import Position

from ditto_backtest.manifest import RunManifest

__all__ = [
    "BacktestAccountStateSnapshot",
    "BacktestCheckpoint",
    "BacktestDelayedSignalSnapshot",
    "BacktestFrozenQuantitySnapshot",
    "BacktestPendingOrderSnapshot",
    "BacktestPositionSnapshot",
    "BacktestRuntimeStateSnapshot",
    "BacktestSettlementStateSnapshot",
    "BacktestTargetWeightSnapshot",
    "EngineResult",
    "EngineResultBuilder",
]


@dataclass(frozen=True)
class BacktestPositionSnapshot:
    """Checkpoint-safe position snapshot."""

    instrument_id: InstrumentId
    quantity: int
    available_quantity: int
    average_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_fees: float

    @classmethod
    def from_position(cls, position: Position) -> BacktestPositionSnapshot:
        """Convert portfolio Position into a checkpoint-safe snapshot."""
        return cls(
            instrument_id=position.instrument_id,
            quantity=position.quantity,
            available_quantity=position.available_quantity,
            average_cost=position.average_cost,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            total_fees=position.total_fees,
        )

    def to_payload(self) -> dict[str, int | float]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "instrument_id": int(self.instrument_id),
            "quantity": self.quantity,
            "available_quantity": self.available_quantity,
            "average_cost": float(self.average_cost),
            "market_value": float(self.market_value),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "total_fees": float(self.total_fees),
        }

    @classmethod
    def from_payload(cls, payload: object) -> BacktestPositionSnapshot:
        """Deserialize a checkpoint-safe position snapshot payload."""
        data = _payload_mapping(payload)
        return cls(
            instrument_id=InstrumentId(_payload_int(data, "instrument_id")),
            quantity=_payload_int(data, "quantity"),
            available_quantity=_payload_int(data, "available_quantity"),
            average_cost=_payload_float(data, "average_cost"),
            market_value=_payload_float(data, "market_value"),
            unrealized_pnl=_payload_float(data, "unrealized_pnl"),
            realized_pnl=_payload_float(data, "realized_pnl"),
            total_fees=_payload_float(data, "total_fees"),
        )


@dataclass(frozen=True)
class BacktestAccountStateSnapshot:
    """Checkpoint-safe account state snapshot for future state-restored resume."""

    cash_available: float
    cash_settled: float
    cash_frozen: float
    total_value: float
    nav: float
    exposure: float
    positions: tuple[BacktestPositionSnapshot, ...] = ()

    @classmethod
    def from_account_view(
        cls,
        account_view: AccountView,
    ) -> BacktestAccountStateSnapshot:
        """Convert AccountView into a deterministic checkpoint payload."""
        return cls(
            cash_available=account_view.cash.available,
            cash_settled=account_view.cash.settled,
            cash_frozen=account_view.cash.frozen,
            total_value=account_view.total_value,
            nav=account_view.nav,
            exposure=account_view.exposure,
            positions=_snapshot_positions(account_view.positions),
        )

    def to_payload(self) -> dict[str, object]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "cash_available": float(self.cash_available),
            "cash_settled": float(self.cash_settled),
            "cash_frozen": float(self.cash_frozen),
            "total_value": float(self.total_value),
            "nav": float(self.nav),
            "exposure": float(self.exposure),
            "positions": [position.to_payload() for position in self.positions],
        }

    def to_json(self) -> str:
        """Serialize the account state with deterministic key ordering."""
        return orjson.dumps(self.to_payload(), option=orjson.OPT_SORT_KEYS).decode(
            "utf-8"
        )

    @property
    def state_hash(self) -> str:
        """Stable content hash for replay/resume evidence."""
        digest = sha256(self.to_json().encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_payload(cls, payload: object) -> BacktestAccountStateSnapshot:
        """Deserialize an account-state checkpoint payload."""
        data = _payload_mapping(payload)
        return cls(
            cash_available=_payload_float(data, "cash_available"),
            cash_settled=_payload_float(data, "cash_settled"),
            cash_frozen=_payload_float(data, "cash_frozen"),
            total_value=_payload_float(data, "total_value"),
            nav=_payload_float(data, "nav"),
            exposure=_payload_float(data, "exposure"),
            positions=tuple(
                BacktestPositionSnapshot.from_payload(position)
                for position in _payload_sequence(data, "positions")
            ),
        )

    @classmethod
    def from_json(cls, payload_json: str) -> BacktestAccountStateSnapshot:
        """Deserialize deterministic account-state JSON."""
        return cls.from_payload(cast(object, orjson.loads(payload_json)))


def _snapshot_positions(
    positions: Mapping[InstrumentId, Position],
) -> tuple[BacktestPositionSnapshot, ...]:
    """Return deterministic position snapshots sorted by instrument ID."""
    return tuple(
        BacktestPositionSnapshot.from_position(position)
        for _instrument_id, position in sorted(
            positions.items(),
            key=lambda item: int(item[0]),
        )
    )


@dataclass(frozen=True)
class BacktestFrozenQuantitySnapshot:
    """Checkpoint-safe settlement frozen quantity snapshot."""

    instrument_id: InstrumentId
    settle_date: str
    quantity: int

    def to_payload(self) -> dict[str, int | str]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "instrument_id": int(self.instrument_id),
            "quantity": self.quantity,
            "settle_date": self.settle_date,
        }

    @classmethod
    def from_payload(cls, payload: object) -> BacktestFrozenQuantitySnapshot:
        """Deserialize a settlement frozen-quantity checkpoint payload."""
        data = _payload_mapping(payload)
        return cls(
            instrument_id=InstrumentId(_payload_int(data, "instrument_id")),
            settle_date=_payload_str(data, "settle_date"),
            quantity=_payload_int(data, "quantity"),
        )


@dataclass(frozen=True)
class BacktestSettlementStateSnapshot:
    """Checkpoint-safe settlement state snapshot for future state-restored resume."""

    frozen_quantities: tuple[BacktestFrozenQuantitySnapshot, ...] = ()

    @classmethod
    def from_frozen_quantities(
        cls,
        frozen_quantities: Mapping[InstrumentId, Mapping[str, int]],
    ) -> BacktestSettlementStateSnapshot:
        """Convert brokerage frozen-quantity state into deterministic payload."""
        return cls(
            frozen_quantities=_snapshot_frozen_quantities(frozen_quantities),
        )

    def to_payload(self) -> dict[str, object]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "frozen_quantities": [
                frozen.to_payload() for frozen in self.frozen_quantities
            ],
        }

    def to_json(self) -> str:
        """Serialize the settlement state with deterministic key ordering."""
        return orjson.dumps(self.to_payload(), option=orjson.OPT_SORT_KEYS).decode(
            "utf-8"
        )

    @property
    def state_hash(self) -> str:
        """Stable content hash for replay/resume evidence."""
        digest = sha256(self.to_json().encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_payload(cls, payload: object) -> BacktestSettlementStateSnapshot:
        """Deserialize a settlement-state checkpoint payload."""
        data = _payload_mapping(payload)
        return cls(
            frozen_quantities=tuple(
                BacktestFrozenQuantitySnapshot.from_payload(frozen)
                for frozen in _payload_sequence(data, "frozen_quantities")
            )
        )

    @classmethod
    def from_json(cls, payload_json: str) -> BacktestSettlementStateSnapshot:
        """Deserialize deterministic settlement-state JSON."""
        return cls.from_payload(cast(object, orjson.loads(payload_json)))


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
        """Convert an execution ticket into deterministic checkpoint payload."""
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
            "average_fill_price": self.average_fill_price,
            "client_order_id": self.client_order_id,
            "direction": self.direction,
            "filled_price": self.filled_price,
            "filled_quantity": self.filled_quantity,
            "instrument_id": int(self.instrument_id),
            "leaves_quantity": self.leaves_quantity,
            "order_type": self.order_type,
            "price": self.price,
            "quantity": self.quantity,
            "status": self.status,
            "stop_price": self.stop_price,
            "trade_date": self.trade_date,
        }

    @classmethod
    def from_payload(cls, payload: object) -> BacktestPendingOrderSnapshot:
        """Deserialize a pending-order checkpoint payload."""
        data = _payload_mapping(payload)
        return cls(
            client_order_id=_payload_str(data, "client_order_id"),
            instrument_id=InstrumentId(_payload_int(data, "instrument_id")),
            order_type=_payload_str(data, "order_type"),
            direction=_payload_str(data, "direction"),
            quantity=_payload_int(data, "quantity"),
            price=_payload_optional_float(data, "price"),
            stop_price=_payload_optional_float(data, "stop_price"),
            trade_date=_payload_optional_str(data, "trade_date"),
            status=_payload_str(data, "status"),
            filled_quantity=_payload_int(data, "filled_quantity"),
            leaves_quantity=_payload_int(data, "leaves_quantity"),
            filled_price=_payload_optional_float(data, "filled_price"),
            average_fill_price=_payload_optional_float(data, "average_fill_price"),
        )


@dataclass(frozen=True)
class BacktestTargetWeightSnapshot:
    """Checkpoint-safe target weight snapshot for a delayed signal."""

    instrument_id: InstrumentId
    target_weight: float

    def to_payload(self) -> dict[str, int | float]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "instrument_id": int(self.instrument_id),
            "target_weight": self.target_weight,
        }

    @classmethod
    def from_payload(cls, payload: object) -> BacktestTargetWeightSnapshot:
        """Deserialize a delayed-signal target-weight payload."""
        data = _payload_mapping(payload)
        return cls(
            instrument_id=InstrumentId(_payload_int(data, "instrument_id")),
            target_weight=_payload_float(data, "target_weight"),
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

    @classmethod
    def from_signal(
        cls,
        queue_index: int,
        signal: object,
    ) -> BacktestDelayedSignalSnapshot:
        """Convert TargetPortfolio-like signal into deterministic payload."""
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
            "cash_target": self.cash_target,
            "positions": [position.to_payload() for position in self.positions],
            "queue_index": self.queue_index,
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "trade_date": self.trade_date,
        }

    @classmethod
    def from_payload(cls, payload: object) -> BacktestDelayedSignalSnapshot:
        """Deserialize a delayed-signal checkpoint payload."""
        data = _payload_mapping(payload)
        return cls(
            queue_index=_payload_int(data, "queue_index"),
            trade_date=_payload_str(data, "trade_date"),
            strategy_id=_payload_str(data, "strategy_id"),
            run_id=_payload_str(data, "run_id"),
            cash_target=_payload_float(data, "cash_target"),
            positions=tuple(
                BacktestTargetWeightSnapshot.from_payload(position)
                for position in _payload_sequence(data, "positions")
            ),
        )


@dataclass(frozen=True)
class BacktestRuntimeStateSnapshot:
    """Checkpoint-safe engine runtime state snapshot for future restore."""

    pending_orders: tuple[BacktestPendingOrderSnapshot, ...] = ()
    delayed_signals: tuple[BacktestDelayedSignalSnapshot, ...] = ()

    @classmethod
    def from_state(
        cls,
        *,
        pending_tickets: tuple[OrderTicket, ...] = (),
        delayed_signals: tuple[object, ...] = (),
    ) -> BacktestRuntimeStateSnapshot:
        """Convert runtime queues into deterministic checkpoint payload."""
        return cls(
            pending_orders=_snapshot_pending_orders(pending_tickets),
            delayed_signals=tuple(
                BacktestDelayedSignalSnapshot.from_signal(index, signal)
                for index, signal in enumerate(delayed_signals)
            ),
        )

    def to_payload(self) -> dict[str, object]:
        """Return stable JSON payload for persistence and hashing."""
        return {
            "delayed_signals": [signal.to_payload() for signal in self.delayed_signals],
            "pending_orders": [order.to_payload() for order in self.pending_orders],
        }

    def to_json(self) -> str:
        """Serialize the runtime state with deterministic key ordering."""
        return orjson.dumps(self.to_payload(), option=orjson.OPT_SORT_KEYS).decode(
            "utf-8"
        )

    @property
    def state_hash(self) -> str:
        """Stable content hash for replay/resume evidence."""
        digest = sha256(self.to_json().encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_payload(cls, payload: object) -> BacktestRuntimeStateSnapshot:
        """Deserialize a runtime-state checkpoint payload."""
        data = _payload_mapping(payload)
        return cls(
            pending_orders=tuple(
                BacktestPendingOrderSnapshot.from_payload(order)
                for order in _payload_sequence(data, "pending_orders")
            ),
            delayed_signals=tuple(
                BacktestDelayedSignalSnapshot.from_payload(signal)
                for signal in _payload_sequence(data, "delayed_signals")
            ),
        )

    @classmethod
    def from_json(cls, payload_json: str) -> BacktestRuntimeStateSnapshot:
        """Deserialize deterministic runtime-state JSON."""
        return cls.from_payload(cast(object, orjson.loads(payload_json)))


def _payload_mapping(payload: object) -> Mapping[str, object]:
    """Return payload as a string-keyed mapping or raise a checkpoint error."""
    if not isinstance(payload, Mapping):
        msg = "checkpoint payload must be an object"
        raise ValueError(msg)
    return cast(Mapping[str, object], payload)


def _payload_sequence(
    payload: Mapping[str, object],
    key: str,
) -> tuple[object, ...]:
    """Read a list-like checkpoint field."""
    value = payload.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"checkpoint field {key!r} must be a sequence"
        raise ValueError(msg)
    return tuple(cast(Sequence[object], value))


def _payload_str(payload: Mapping[str, object], key: str) -> str:
    """Read a required string checkpoint field."""
    value = _payload_required(payload, key)
    if not isinstance(value, str):
        msg = f"checkpoint field {key!r} must be a string"
        raise ValueError(msg)
    return value


def _payload_optional_str(payload: Mapping[str, object], key: str) -> str | None:
    """Read an optional string checkpoint field."""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"checkpoint field {key!r} must be a string or null"
        raise ValueError(msg)
    return value


def _payload_int(payload: Mapping[str, object], key: str) -> int:
    """Read a required integer checkpoint field."""
    value = _payload_required(payload, key)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"checkpoint field {key!r} must be an integer"
        raise ValueError(msg)
    return value


def _payload_float(payload: Mapping[str, object], key: str) -> float:
    """Read a required numeric checkpoint field."""
    value = _payload_required(payload, key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"checkpoint field {key!r} must be numeric"
        raise ValueError(msg)
    return float(value)


def _payload_optional_float(
    payload: Mapping[str, object],
    key: str,
) -> float | None:
    """Read an optional numeric checkpoint field."""
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"checkpoint field {key!r} must be numeric or null"
        raise ValueError(msg)
    return float(value)


def _payload_required(payload: Mapping[str, object], key: str) -> object:
    """Read a required checkpoint field."""
    if key not in payload:
        msg = f"checkpoint field {key!r} is required"
        raise ValueError(msg)
    return payload[key]


def _snapshot_pending_orders(
    pending_tickets: tuple[OrderTicket, ...],
) -> tuple[BacktestPendingOrderSnapshot, ...]:
    """Return deterministic pending-order snapshots sorted by client order ID."""
    return tuple(
        BacktestPendingOrderSnapshot.from_ticket(ticket)
        for ticket in sorted(
            pending_tickets,
            key=lambda item: item.order.client_id.value,
        )
    )


def _snapshot_target_weights(
    positions: object,
) -> tuple[BacktestTargetWeightSnapshot, ...]:
    """Return deterministic delayed-signal weights sorted by instrument ID."""
    if not isinstance(positions, Mapping):
        return ()
    typed_positions = cast(Mapping[object, object], positions)
    snapshots: list[BacktestTargetWeightSnapshot] = []
    for instrument_id, target_weight in typed_positions.items():
        if not isinstance(instrument_id, int | str):
            continue
        if not isinstance(target_weight, int | float):
            continue
        snapshots.append(
            BacktestTargetWeightSnapshot(
                instrument_id=InstrumentId(int(instrument_id)),
                target_weight=float(target_weight),
            )
        )
    return tuple(
        sorted(
            snapshots,
            key=lambda item: int(item.instrument_id),
        )
    )


def _snapshot_frozen_quantities(
    frozen_quantities: Mapping[InstrumentId, Mapping[str, int]],
) -> tuple[BacktestFrozenQuantitySnapshot, ...]:
    """Return deterministic settlement freeze snapshots sorted by ID/date."""
    snapshots: list[BacktestFrozenQuantitySnapshot] = []
    for instrument_id, date_quantities in frozen_quantities.items():
        for settle_date, quantity in date_quantities.items():
            if quantity <= 0:
                continue
            snapshots.append(
                BacktestFrozenQuantitySnapshot(
                    instrument_id=instrument_id,
                    settle_date=settle_date,
                    quantity=quantity,
                )
            )
    return tuple(
        sorted(
            snapshots,
            key=lambda item: (int(item.instrument_id), item.settle_date),
        )
    )


@dataclass(frozen=True)
class BacktestCheckpoint:
    """
    回测恢复 checkpoint -- 不可变.

    表示已完成到哪个交易日，以及下一次恢复应从哪个交易日开始。
    该对象不包含存储行为；持久化由 application/apps 层通过回调接管。
    """

    run_id: str
    strategy_id: str
    completed_trade_date: str
    resume_from: str | None
    completed_days: int
    total_days: int
    nav: float
    fill_count: int
    order_count: int
    account_state: BacktestAccountStateSnapshot | None = None
    settlement_state: BacktestSettlementStateSnapshot | None = None
    runtime_state: BacktestRuntimeStateSnapshot | None = None

    @property
    def can_resume(self) -> bool:
        """是否仍有后续交易日可恢复执行。"""
        return self.resume_from is not None

    @property
    def account_state_json(self) -> str:
        """Serialized account state snapshot, empty when not captured."""
        if self.account_state is None:
            return ""
        return self.account_state.to_json()

    @property
    def account_state_hash(self) -> str:
        """Stable hash of account_state_json, empty when not captured."""
        if self.account_state is None:
            return ""
        return self.account_state.state_hash

    @property
    def settlement_state_json(self) -> str:
        """Serialized settlement state snapshot, empty when not captured."""
        if self.settlement_state is None:
            return ""
        return self.settlement_state.to_json()

    @property
    def settlement_state_hash(self) -> str:
        """Stable hash of settlement_state_json, empty when not captured."""
        if self.settlement_state is None:
            return ""
        return self.settlement_state.state_hash

    @property
    def runtime_state_json(self) -> str:
        """Serialized engine runtime state snapshot, empty when not captured."""
        if self.runtime_state is None:
            return ""
        return self.runtime_state.to_json()

    @property
    def runtime_state_hash(self) -> str:
        """Stable hash of runtime_state_json, empty when not captured."""
        if self.runtime_state is None:
            return ""
        return self.runtime_state.state_hash


@dataclass(frozen=True)
class EngineResult:
    """
    引擎运行结果 -- 不可变.

    产出后不可修改；运行过程中的可变累积由 EngineResultBuilder 负责。

    Attributes:
        run_id: 运行唯一 ID
        period: (start_date, end_date)
        final_nav: 最终净值
        total_trades: 总成交笔数
        orders: 所有提交的订单（tuple，不可变）
        fills: 所有成交事件（tuple，不可变）
        account_view: 最终账户快照
        manifest: 运行清单 (None = 未启用 RuleRefCollector)
        skipped_dates: Step 失败被跳过的日期
        last_checkpoint: 最后一个成功交易日的恢复 checkpoint
        cancelled: 是否被协作式取消

    """

    run_id: str
    period: tuple[str, str]
    final_nav: float = 0.0
    total_trades: int = 0
    orders: tuple[Order, ...] = ()
    fills: tuple[FillEvent, ...] = ()
    account_view: AccountView | None = None
    manifest: RunManifest | None = None
    skipped_dates: tuple[str, ...] = ()
    last_checkpoint: BacktestCheckpoint | None = None
    cancelled: bool = False


@dataclass
class EngineResultBuilder:
    """
    EngineResult 可变累积器 -- 运行过程中逐步收集 orders/fills/skipped.

    通过 build() 方法产出不可变的 EngineResult。
    """

    orders: list[Order] = field(default_factory=list)
    fills: list[FillEvent] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def add_order(self, order: Order) -> None:
        """追加单个订单。"""
        self.orders.append(order)

    def add_fill(self, fill: FillEvent) -> None:
        """追加单个成交。"""
        self.fills.append(fill)

    def add_skipped(self, date: str) -> None:
        """追加一个跳过日期。"""
        self.skipped.append(date)

    def extend_orders(self, orders: list[Order]) -> None:
        """批量追加订单。"""
        self.orders.extend(orders)

    def extend_fills(self, fills: list[FillEvent]) -> None:
        """批量追加成交。"""
        self.fills.extend(fills)

    def build(
        self,
        *,
        run_id: str,
        period: tuple[str, str],
        final_nav: float,
        account_view: AccountView | None = None,
        manifest: RunManifest | None = None,
        last_checkpoint: BacktestCheckpoint | None = None,
        cancelled: bool = False,
    ) -> EngineResult:
        """将累积状态转换为不可变的 EngineResult。"""
        return EngineResult(
            run_id=run_id,
            period=period,
            final_nav=final_nav,
            total_trades=len(self.fills),
            orders=tuple(self.orders),
            fills=tuple(self.fills),
            account_view=account_view,
            manifest=manifest,
            skipped_dates=tuple(self.skipped),
            last_checkpoint=last_checkpoint,
            cancelled=cancelled,
        )
