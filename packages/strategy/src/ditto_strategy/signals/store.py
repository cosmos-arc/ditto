from __future__ import annotations

from typing import Protocol

from ditto_strategy.signals.models import SignalRecord

__all__ = ["SignalStore"]


class SignalStore(Protocol):
    """Persist and load strategy signal batches."""

    def save_signal(self, record: SignalRecord) -> None:
        """Persist one strategy signal record."""
        ...

    def list_signals(
        self,
        strategy_id: str,
        trade_date: str | None = None,
    ) -> list[SignalRecord]:
        """List signal records for a strategy, optionally scoped to a date."""
        ...
