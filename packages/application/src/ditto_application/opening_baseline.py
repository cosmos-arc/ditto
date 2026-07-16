"""Neutral application contract for one manual execution opening baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_execution.models import AccountSnapshotRecord, PositionRecord, SignalRecord

__all__ = ["OpeningBaseline", "OpeningBaselinePort"]


@dataclass(frozen=True)
class OpeningBaseline:
    """Exact account aggregate used as the opening state for fill replay."""

    account: AccountSnapshotRecord
    positions: tuple[PositionRecord, ...]


class OpeningBaselinePort(Protocol):
    """Resolve one intent to its exact, complete opening account aggregate."""

    def resolve(self, intent: SignalRecord) -> OpeningBaseline:
        """Return the latest complete baseline no later than the signal date."""
        ...
