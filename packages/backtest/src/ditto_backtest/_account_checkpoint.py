"""Acyclic account checkpoint DTOs shared by results and audit state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting import AccountView
from ditto_portfolio.accounting.position import Position

from ditto_backtest._checkpoint_codec import (
    finite_float,
    payload_float,
    payload_int,
    payload_mapping,
    payload_sequence,
)

__all__ = ["BacktestAccountStateSnapshot", "BacktestPositionSnapshot"]


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
            "average_cost": finite_float(self.average_cost, "average_cost"),
            "market_value": finite_float(self.market_value, "market_value"),
            "unrealized_pnl": finite_float(self.unrealized_pnl, "unrealized_pnl"),
            "realized_pnl": finite_float(self.realized_pnl, "realized_pnl"),
            "total_fees": finite_float(self.total_fees, "total_fees"),
        }

    @classmethod
    def from_payload(cls, payload: object) -> BacktestPositionSnapshot:
        """Deserialize a checkpoint-safe position snapshot payload."""
        data = payload_mapping(payload)
        return cls(
            instrument_id=InstrumentId(payload_int(data, "instrument_id")),
            quantity=payload_int(data, "quantity"),
            available_quantity=payload_int(data, "available_quantity"),
            average_cost=payload_float(data, "average_cost"),
            market_value=payload_float(data, "market_value"),
            unrealized_pnl=payload_float(data, "unrealized_pnl"),
            realized_pnl=payload_float(data, "realized_pnl"),
            total_fees=payload_float(data, "total_fees"),
        )


@dataclass(frozen=True)
class BacktestAccountStateSnapshot:
    """Checkpoint-safe account state snapshot for exact resume."""

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
            "cash_available": finite_float(self.cash_available, "cash_available"),
            "cash_settled": finite_float(self.cash_settled, "cash_settled"),
            "cash_frozen": finite_float(self.cash_frozen, "cash_frozen"),
            "total_value": finite_float(self.total_value, "total_value"),
            "nav": finite_float(self.nav, "nav"),
            "exposure": finite_float(self.exposure, "exposure"),
            "positions": [position.to_payload() for position in self.positions],
        }

    def to_json(self) -> str:
        """Serialize the account state with deterministic key ordering."""
        return orjson.dumps(self.to_payload(), option=orjson.OPT_SORT_KEYS).decode()

    @property
    def state_hash(self) -> str:
        """Stable content hash for replay/resume evidence."""
        digest = sha256(self.to_json().encode()).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_payload(cls, payload: object) -> BacktestAccountStateSnapshot:
        """Deserialize an account-state checkpoint payload."""
        data = payload_mapping(payload)
        return cls(
            cash_available=payload_float(data, "cash_available"),
            cash_settled=payload_float(data, "cash_settled"),
            cash_frozen=payload_float(data, "cash_frozen"),
            total_value=payload_float(data, "total_value"),
            nav=payload_float(data, "nav"),
            exposure=payload_float(data, "exposure"),
            positions=tuple(
                BacktestPositionSnapshot.from_payload(position)
                for position in payload_sequence(data, "positions")
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
