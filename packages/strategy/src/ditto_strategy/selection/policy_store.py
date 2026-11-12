"""Persistence ports for immutable SelectionSpec policy snapshots."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.selection.contracts import EtfSelectionSpec, StockSelectionSpec

__all__ = ["SelectionPolicyReader", "SelectionPolicyStore", "SelectionPolicyWriter"]


@runtime_checkable
class SelectionPolicyWriter(Protocol):
    """Append-only write side for content-addressed selection policies."""

    def save_policy(self, value: StockSelectionSpec | EtfSelectionSpec) -> None:
        """Persist one exact policy keyed by its canonical hash; replay is a no-op."""
        ...


@runtime_checkable
class SelectionPolicyReader(Protocol):
    """Exact read side for content-addressed selection policies."""

    def policy_by_hash(
        self, spec_hash: str
    ) -> StockSelectionSpec | EtfSelectionSpec | None:
        """Return the exact policy for one hash, or None when never saved."""
        ...


@runtime_checkable
class SelectionPolicyStore(SelectionPolicyReader, SelectionPolicyWriter, Protocol):
    """Combined store port used only at composition boundaries."""
