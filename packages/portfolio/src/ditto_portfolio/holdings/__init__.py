"""Holdings — 持仓快照与追踪。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__all__ = ["HoldingReader", "HoldingSnapshot"]


@dataclass(frozen=True)
class HoldingSnapshot:
    """Valuation snapshot for an account holding."""

    account_id: str
    snapshot_date: str
    instrument_id: int
    quantity: int
    available_quantity: int
    market_value: float
    weight: float


class HoldingReader(Protocol):
    """Read-only holding snapshot contract."""

    def get_holding(
        self,
        account_id: str,
        instrument_id: int,
        snapshot_date: str,
    ) -> HoldingSnapshot | None:
        """Return one holding snapshot if available."""
        ...

    def list_holdings(
        self,
        account_id: str,
        snapshot_date: str,
    ) -> list[HoldingSnapshot]:
        """Return all holding snapshots for an account and date."""
        ...
