"""Product-neutral data lineage contract types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ditto_data.catalog.contracts import DataAssetRef

__all__ = [
    "DataLineageReader",
    "DataLineageRecorder",
    "LineageEvent",
    "LineageInputRef",
    "LineageOutputRef",
]


@dataclass(frozen=True)
class LineageInputRef:
    """Input asset reference for a lineage event."""

    asset: DataAssetRef
    role: str = "input"


@dataclass(frozen=True)
class LineageOutputRef:
    """Output asset reference for a lineage event."""

    asset: DataAssetRef
    role: str = "output"


@dataclass(frozen=True)
class LineageEvent:
    """Recorded transformation or ingestion relationship between assets."""

    run_id: str
    operation: str
    inputs: tuple[LineageInputRef, ...]
    outputs: tuple[LineageOutputRef, ...]
    timestamp: datetime


@runtime_checkable
class DataLineageRecorder(Protocol):
    """Append-only lineage event recorder."""

    def record_event(self, event: LineageEvent) -> None:
        """Record a lineage event."""
        ...


@runtime_checkable
class DataLineageReader(Protocol):
    """Read-only access to recorded lineage events."""

    def list_events_for_asset(self, asset: DataAssetRef) -> tuple[LineageEvent, ...]:
        """Return lineage events that mention an asset."""
        ...
