"""Tests for UnitOfWork and AtomicWriter abstractions."""

from __future__ import annotations

import pytest
from ditto_data.stores.runtime.unit_of_work import (
    AtomicWriter,
    SQLiteAtomicWriter,
    UnitOfWork,
)


class MockAtomicWriter:
    """In-memory AtomicWriter for testing."""

    def __init__(self, fail_on_commit: bool = False) -> None:
        self.committed = False
        self.rolled_back = False
        self.begin_called = False
        self.commit_calls = 0
        self._fail_on_commit = fail_on_commit

    def begin(self) -> None:
        self.begin_called = True

    def commit(self) -> None:
        self.commit_calls += 1
        if self._fail_on_commit:
            raise RuntimeError("commit failure")
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class TestUnitOfWork:
    """Tests for UnitOfWork."""

    def test_commit_executes_all_operations(self) -> None:
        """All enqueued operations should execute on commit."""
        writer = MockAtomicWriter()
        uow = UnitOfWork(writer)
        results: list[str] = []

        uow.enqueue(lambda: results.append("a"))
        uow.enqueue(lambda: results.append("b"))
        uow.enqueue(lambda: results.append("c"))

        uow.commit()

        assert results == ["a", "b", "c"]
        assert uow.is_committed
        assert writer.begin_called
        assert writer.committed

    def test_empty_commit_succeeds(self) -> None:
        """Committing with no operations should succeed."""
        writer = MockAtomicWriter()
        uow = UnitOfWork(writer)

        uow.commit()

        assert uow.is_committed
        assert writer.begin_called

    def test_rollback_on_operation_failure(self) -> None:
        """Failure during operation should trigger rollback and re-raise."""
        writer = MockAtomicWriter()
        uow = UnitOfWork(writer)
        results: list[str] = []

        uow.enqueue(lambda: results.append("a"))
        uow.enqueue(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        with pytest.raises(RuntimeError, match="boom"):
            uow.commit()

        assert results == ["a"]
        assert writer.rolled_back
        assert not uow.is_committed
        assert not writer.committed

    def test_rollback_on_commit_failure(self) -> None:
        """Failure during commit should trigger rollback."""
        writer = MockAtomicWriter(fail_on_commit=True)
        uow = UnitOfWork(writer)
        results: list[str] = []

        uow.enqueue(lambda: results.append("a"))

        with pytest.raises(RuntimeError, match="commit failure"):
            uow.commit()

        assert results == ["a"]
        assert writer.rolled_back
        assert not uow.is_committed

    def test_cannot_enqueue_after_commit(self) -> None:
        """Enqueueing after commit should raise RuntimeError."""
        writer = MockAtomicWriter()
        uow = UnitOfWork(writer)

        uow.enqueue(lambda: None)
        uow.commit()

        with pytest.raises(RuntimeError, match="Cannot enqueue after commit"):
            uow.enqueue(lambda: None)

    def test_operations_not_executed_before_commit(self) -> None:
        """Operations should only execute during commit, not when enqueued."""
        writer = MockAtomicWriter()
        uow = UnitOfWork(writer)
        results: list[str] = []

        uow.enqueue(lambda: results.append("a"))
        uow.enqueue(lambda: results.append("b"))

        assert results == []

    def test_protocol_conformance(self) -> None:
        """MockAtomicWriter should satisfy the AtomicWriter protocol."""
        writer = MockAtomicWriter()
        assert isinstance(writer, AtomicWriter)


class TestSQLiteAtomicWriter:
    """Tests for SQLiteAtomicWriter."""

    def test_begin_commit_cycle(self) -> None:
        """Begin should mark active; commit should delegate and clear."""
        committed = False
        rolled_back = False

        class FakeSQLiteClient:
            def commit(self) -> None:
                nonlocal committed
                committed = True

            def rollback(self) -> None:
                nonlocal rolled_back
                rolled_back = True

        client = FakeSQLiteClient()
        writer = SQLiteAtomicWriter(client)

        writer.begin()
        writer.commit()

        assert committed
        assert not rolled_back

    def test_begin_rollback_cycle(self) -> None:
        """Rollback should delegate and clear active state."""
        rolled_back = False

        class FakeSQLiteClient:
            def commit(self) -> None: ...

            def rollback(self) -> None:
                nonlocal rolled_back
                rolled_back = True

        client = FakeSQLiteClient()
        writer = SQLiteAtomicWriter(client)

        writer.begin()
        writer.rollback()

        assert rolled_back

    def test_rollback_without_begin_is_noop(self) -> None:
        """Rollback without begin should not call client rollback."""
        rolled_back = False

        class FakeSQLiteClient:
            def commit(self) -> None: ...

            def rollback(self) -> None:
                nonlocal rolled_back
                rolled_back = True

        client = FakeSQLiteClient()
        writer = SQLiteAtomicWriter(client)

        writer.rollback()

        assert not rolled_back

    def test_commit_without_begin_is_noop(self) -> None:
        """Commit without begin should not call client commit."""
        committed = False

        class FakeSQLiteClient:
            def commit(self) -> None:
                nonlocal committed
                committed = True

            def rollback(self) -> None: ...

        client = FakeSQLiteClient()
        writer = SQLiteAtomicWriter(client)

        writer.commit()

        assert not committed

    def test_protocol_conformance(self) -> None:
        """SQLiteAtomicWriter should satisfy the AtomicWriter protocol."""
        committed = False
        rolled_back = False

        class FakeSQLiteClient:
            def commit(self) -> None:
                nonlocal committed
                committed = True

            def rollback(self) -> None:
                nonlocal rolled_back
                rolled_back = True

        client = FakeSQLiteClient()
        writer = SQLiteAtomicWriter(client)
        assert isinstance(writer, AtomicWriter)
