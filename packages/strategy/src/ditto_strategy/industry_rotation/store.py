"""Persistence ports owned by immutable industry-rotation snapshots."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.industry_rotation.contracts import IndustryRotationSnapshot

__all__ = ["IndustryRotationReader", "IndustryRotationWriter"]


@runtime_checkable
class IndustryRotationReader(Protocol):
    """Exact read side for content-addressed rotation snapshots."""

    def get_rotation(self, snapshot_id: str) -> IndustryRotationSnapshot | None:
        """Return one exact authenticated snapshot when present."""
        ...


@runtime_checkable
class IndustryRotationWriter(Protocol):
    """Append-only write side for rotation evidence."""

    def save_rotation(self, value: IndustryRotationSnapshot) -> None:
        """Persist an exact snapshot idempotently without replacement."""
        ...
