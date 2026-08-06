"""Backtest engine result model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import cast

import orjson
from ditto_execution.orders.model import Order
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_backtest._account_checkpoint import (
    BacktestAccountStateSnapshot,
    BacktestPositionSnapshot,
)
from ditto_backtest._checkpoint_codec import (
    payload_int as _payload_int,
)
from ditto_backtest._checkpoint_codec import (
    payload_mapping as _payload_mapping,
)
from ditto_backtest._checkpoint_codec import (
    payload_sequence as _payload_sequence,
)
from ditto_backtest._checkpoint_codec import (
    payload_str as _payload_str,
)
from ditto_backtest.manifest import RunManifest
from ditto_backtest.runtime_state import (
    BacktestDelayedSignalSnapshot,
    BacktestPendingOrderSnapshot,
    BacktestRuntimeStateCapture,
    BacktestRuntimeStateSnapshot,
    BacktestStrategyContextSnapshot,
    BacktestTargetWeightSnapshot,
)

__all__ = [
    "BacktestAccountStateSnapshot",
    "BacktestCheckpoint",
    "BacktestDelayedSignalSnapshot",
    "BacktestFrozenQuantitySnapshot",
    "BacktestPendingOrderSnapshot",
    "BacktestPositionSnapshot",
    "BacktestRuntimeStateCapture",
    "BacktestRuntimeStateSnapshot",
    "BacktestSettlementStateSnapshot",
    "BacktestStrategyContextSnapshot",
    "BacktestTargetWeightSnapshot",
    "EngineResult",
    "EngineResultBuilder",
]


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
