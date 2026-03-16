"""
UnitOfWork pattern for atomic multi-step write operations.

Provides abstractions for batching multiple write operations into a single
atomic transaction, with support for rollback on failure.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

__all__ = [
    "AtomicWriter",
    "SQLiteAtomicWriter",
    "UnitOfWork",
]


@runtime_checkable
class AtomicWriter(Protocol):
    """Protocol for transactional write backends."""

    def begin(self) -> None:
        """Begin a transaction."""

    def commit(self) -> None:
        """Commit the transaction."""

    def rollback(self) -> None:
        """Rollback the transaction."""


class UnitOfWork:
    """
    Queues operations and commits them atomically via an AtomicWriter.

    Usage::

        writer = SQLiteAtomicWriter(sqlite_client)
        uow = UnitOfWork(writer)
        uow.enqueue(lambda: sqlite_client.execute("INSERT ...", (...,)))
        uow.enqueue(lambda: sqlite_client.execute("UPDATE ...", (...,)))
        uow.commit()  # All or nothing

    Attributes:
        is_committed: Whether the unit of work has been committed.

    """

    def __init__(self, writer: AtomicWriter) -> None:
        self._writer = writer
        self._operations: list[Callable[[], None]] = []
        self._committed = False

    def enqueue(self, operation: Callable[[], None]) -> None:
        """
        Add an operation to the batch.

        Args:
            operation: A no-argument callable to execute during commit.

        Raises:
            RuntimeError: If called after commit.

        """
        if self._committed:
            raise RuntimeError("Cannot enqueue after commit")
        self._operations.append(operation)

    def commit(self) -> None:
        """
        Execute all enqueued operations atomically.

        Begins a transaction, executes all operations in order, then commits.
        If any operation or the commit itself fails, rolls back and re-raises.

        Raises:
            Exception: The original exception from the failing operation.

        """
        self._writer.begin()
        try:
            for op in self._operations:
                op()
            self._writer.commit()
            self._committed = True
        except Exception:
            self._writer.rollback()
            raise

    @property
    def is_committed(self) -> bool:
        """Whether this unit of work has been successfully committed."""
        return self._committed


class _SQLiteCommitRollback(Protocol):
    """Structural interface for SQLite transaction control."""

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class SQLiteAtomicWriter:
    """
    AtomicWriter adapter for SQLiteClient.

    Wraps SQLiteClient's commit/rollback methods, tracking whether a
    transaction is active to avoid no-op calls.

    Args:
        sqlite_client: The SQLiteClient to delegate to.

    """

    def __init__(self, sqlite_client: _SQLiteCommitRollback) -> None:
        """
        Initialize with a SQLiteClient.

        Args:
            sqlite_client: Must expose ``commit()`` and ``rollback()`` methods.

        """
        self._sqlite_client = sqlite_client
        self._active = False

    def begin(self) -> None:
        """Mark the transaction as active."""
        self._active = True

    def commit(self) -> None:
        """
        Commit the active transaction and clear state.

        No-op if no transaction is active (no begin() was called).
        """
        if self._active:
            self._sqlite_client.commit()
            self._active = False

    def rollback(self) -> None:
        """
        Rollback the active transaction and clear state.

        No-op if no transaction is active (no begin() was called).
        """
        if self._active:
            self._sqlite_client.rollback()
            self._active = False
