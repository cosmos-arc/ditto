"""
Hot layer protocols for QuestDB serving and Kvrocks state storage.

Phase 5+ will implement QuestDB-backed hot tables and Kvrocks-backed
state storage. This module defines the interface contracts now so that
consumers can be wired before the infrastructure is ready.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import polars as pl

__all__ = [
    "HotLayerReader",
    "HotLayerWriter",
    "StateStore",
    "UnavailableHotLayerReader",
    "UnavailableHotLayerWriter",
    "UnavailableStateStore",
]


@runtime_checkable
class HotLayerReader(Protocol):
    """
    Read-only access to the hot layer (QuestDB).

    Provides sub-millisecond serving of the latest derived values.
    Implementations must be safe for concurrent reads.
    """

    def is_available(self) -> bool:
        """Check whether the hot layer is reachable."""
        ...

    def read_latest(
        self,
        *,
        derived_id: str,
        instrument_ids: tuple[int, ...] | None,
        as_of: str | None,
    ) -> pl.DataFrame:
        """
        Read the latest values for a derived from the hot layer.

        Args:
            derived_id: The derived spec identifier.
            instrument_ids: Optional filter for specific instruments.
            as_of: Optional point-in-time cutoff (ISO date string).

        Returns:
            A DataFrame with the latest derived values.

        Raises:
            NotImplementedError: If the hot layer is not yet available.

        """
        ...


@runtime_checkable
class HotLayerWriter(Protocol):
    """
    Write access to the hot layer (QuestDB).

    Provides materialization write path for hot tables.
    """

    def write_frame(
        self,
        *,
        derived_id: str,
        version: int,
        frame: pl.DataFrame,
    ) -> int:
        """
        Write a materialized frame to the hot layer.

        Args:
            derived_id: The derived spec identifier.
            version: The version being written.
            frame: The data to write.

        Returns:
            The number of rows written.

        """
        ...


@runtime_checkable
class StateStore(Protocol):
    """
    Key-value state storage (Kvrocks).

    Used for coordination state such as invalidation tokens and
    materialization watermarks.
    """

    def get(self, key: str) -> bytes | None:
        """
        Retrieve a value by key.

        Args:
            key: The state key.

        Returns:
            The stored bytes, or ``None`` if the key does not exist.

        """
        ...

    def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Store a value.

        Args:
            key: The state key.
            value: The bytes to store.
            ttl_seconds: Optional time-to-live in seconds.

        """
        ...


class UnavailableHotLayerReader:
    """
    Placeholder that signals the hot layer is not yet implemented.

    Satisfies the ``HotLayerReader`` protocol. Always reports unavailable
    and raises on any read attempt.
    """

    def is_available(self) -> bool:
        """Return ``False`` — the hot layer is not available."""
        return False

    def read_latest(
        self,
        *,
        derived_id: str,
        instrument_ids: tuple[int, ...] | None,
        as_of: str | None,
    ) -> pl.DataFrame:
        """Raise ``NotImplementedError`` — QuestDB is not wired yet."""
        raise NotImplementedError("Hot layer (QuestDB) is not implemented yet")


class UnavailableHotLayerWriter:
    """
    Placeholder that signals the hot layer writer is not yet implemented.

    Satisfies the ``HotLayerWriter`` protocol. Always raises on any
    write attempt.
    """

    def write_frame(
        self,
        *,
        derived_id: str,
        version: int,
        frame: pl.DataFrame,
    ) -> int:
        """Raise ``NotImplementedError`` — QuestDB is not wired yet."""
        raise NotImplementedError(
            "Hot layer writer (QuestDB) is not implemented yet",
        )


class UnavailableStateStore:
    """
    Placeholder that signals the state store is not yet implemented.

    Satisfies the ``StateStore`` protocol. Always raises on any
    get/set attempt.
    """

    def get(self, key: str) -> bytes | None:
        """Raise ``NotImplementedError`` — Kvrocks is not wired yet."""
        raise NotImplementedError("State store (Kvrocks) is not implemented yet")

    def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        """Raise ``NotImplementedError`` — Kvrocks is not wired yet."""
        raise NotImplementedError("State store (Kvrocks) is not implemented yet")
