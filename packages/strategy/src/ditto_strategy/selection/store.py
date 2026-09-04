"""Persistence ports owned by the saved SelectionRun domain."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.selection.contracts import SelectionRun

__all__ = ["SelectionRunReader", "SelectionRunStore", "SelectionRunWriter"]


@runtime_checkable
class SelectionRunReader(Protocol):
    """Exact read side for immutable saved selection runs."""

    def get(self, run_id: str) -> SelectionRun | None:
        """Return the exact content-addressed run when present."""
        ...

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        """List recent runs for one exact spec family."""
        ...


@runtime_checkable
class SelectionRunWriter(Protocol):
    """Append-only write side for immutable saved selection runs."""

    def save(self, value: SelectionRun) -> None:
        """Persist an exact run idempotently without replacing evidence."""
        ...


@runtime_checkable
class SelectionRunStore(SelectionRunReader, SelectionRunWriter, Protocol):
    """Combined store port used only at composition boundaries."""
