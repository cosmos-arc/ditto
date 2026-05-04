"""Positions — 持仓管理。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__all__ = ["PositionReader", "PositionSnapshot"]


@dataclass(frozen=True)
class PositionSnapshot:
    """Lifecycle-oriented position snapshot."""

    portfolio_id: str
    snapshot_date: str
    instrument_id: int
    quantity: int
    average_cost: float
    market_value: float
    status: str = "open"


class PositionReader(Protocol):
    """Read-only position snapshot contract."""

    def get_position(
        self,
        portfolio_id: str,
        instrument_id: int,
        snapshot_date: str,
    ) -> PositionSnapshot | None:
        """Return one position snapshot if available."""
        ...

    def list_positions(
        self,
        portfolio_id: str,
        snapshot_date: str,
    ) -> list[PositionSnapshot]:
        """Return all position snapshots for a portfolio and date."""
        ...
