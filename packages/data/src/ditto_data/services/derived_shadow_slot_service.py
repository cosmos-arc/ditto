"""Publication shadow slot control-plane service."""

from __future__ import annotations

from typing import Protocol

from ditto_data.models.publication_safety import DerivedShadowSlotRecord


class DerivedShadowSlotReaderProtocol(Protocol):
    """Reader protocol for shadow slot control-plane rows."""

    def read_slot(self, derived_id: str) -> DerivedShadowSlotRecord | None:
        """Read the current slot row for one derived id."""
        ...

    def read_active_slot(self, derived_id: str) -> DerivedShadowSlotRecord | None:
        """Read the active slot row for one derived id."""
        ...


class DerivedShadowSlotWriterProtocol(Protocol):
    """Writer protocol for shadow slot control-plane rows."""

    def write_slot(self, record: DerivedShadowSlotRecord) -> None:
        """Persist or replace the current slot row."""
        ...

    def disable_slot(self, derived_id: str, disabled_at: str) -> None:
        """Disable the active slot for one derived id."""
        ...


class DerivedShadowSlotService:
    """Unified service for derived shadow slot orchestration state."""

    def __init__(
        self,
        *,
        slot_reader: DerivedShadowSlotReaderProtocol,
        slot_writer: DerivedShadowSlotWriterProtocol,
    ) -> None:
        self._slot_reader = slot_reader
        self._slot_writer = slot_writer

    def save_slot(self, record: DerivedShadowSlotRecord) -> None:
        """Persist one slot row."""
        self._slot_writer.write_slot(record)

    def get_slot(self, derived_id: str) -> DerivedShadowSlotRecord | None:
        """Read the current slot row."""
        return self._slot_reader.read_slot(derived_id)

    def get_active_slot(self, derived_id: str) -> DerivedShadowSlotRecord | None:
        """Read the active slot row."""
        return self._slot_reader.read_active_slot(derived_id)

    def disable_slot(self, derived_id: str, disabled_at: str) -> None:
        """Disable the active slot row."""
        self._slot_writer.disable_slot(derived_id, disabled_at)
