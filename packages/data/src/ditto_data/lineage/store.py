"""In-memory data lineage implementation."""

from __future__ import annotations

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.contracts import LineageEvent

__all__ = ["InMemoryDataLineage"]


class InMemoryDataLineage:
    """Append-only in-memory lineage store for tests and development."""

    def __init__(self) -> None:
        self._events: list[LineageEvent] = []

    def record_event(self, event: LineageEvent) -> None:
        """Append one lineage event."""
        self._events.append(event)

    def list_events_for_asset(self, asset: DataAssetRef) -> tuple[LineageEvent, ...]:
        """Return lineage events that mention ``asset`` in append order."""
        return tuple(
            event
            for event in self._events
            if any(ref.asset == asset for ref in event.inputs)
            or any(ref.asset == asset for ref in event.outputs)
        )

    def list_events_for_run(self, run_id: str) -> tuple[LineageEvent, ...]:
        """Return lineage events recorded for ``run_id`` in append order."""
        return tuple(event for event in self._events if event.run_id == run_id)
