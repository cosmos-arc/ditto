"""Fill store — 成交持久化接口。"""

from __future__ import annotations

from typing import Protocol

from ditto_execution.models import FillRecord

__all__ = ["FillStore"]


class FillStore(Protocol):
    """Persistence contract for execution fills."""

    def save_fill(self, record: FillRecord) -> None:
        """Persist one fill record."""
        ...

    def get_fill(self, fill_id: str) -> FillRecord | None:
        """Return one fill by id."""
        ...

    def list_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
    ) -> list[FillRecord]:
        """List fills for a strategy, optionally scoped to a date."""
        ...
