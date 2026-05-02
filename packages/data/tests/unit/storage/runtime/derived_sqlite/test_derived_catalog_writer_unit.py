"""Tests for SQLiteDerivedCatalogWriter — P1-2 record type guards + P1-1 UoW."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_features.models.derived import (
    DerivedRunRecord,
    DerivedVersionRecord,
)
from ditto_features.storage.sqlite.derived.writer import (
    SQLiteDerivedCatalogWriter,
)


def _make_writer() -> SQLiteDerivedCatalogWriter:
    """Create a writer backed by a mock SQLite client."""
    mock_client = MagicMock(spec=SQLiteClient)
    return SQLiteDerivedCatalogWriter(mock_client)


class TestWriteVersionStatusGuard:
    """write_version() must reject invalid version status strings."""

    def test_accepts_valid_status(self) -> None:
        """Valid DerivedVersionStatus values should not raise."""
        writer = _make_writer()
        for status in ("draft", "materialized", "published", "deprecated", "archived"):
            record = DerivedVersionRecord(
                derived_id="factor.test",
                version=1,
                status=status,
                engine_version="1.0",
                is_online=True,
                is_primary=True,
                created_at="2026-03-18T00:00:00+08:00",
                updated_at="2026-03-18T00:00:00+08:00",
            )
            writer.write_version(record)  # should not raise

    def test_rejects_invalid_status(self) -> None:
        """Invalid status string should raise ValueError."""
        writer = _make_writer()
        record = DerivedVersionRecord(
            derived_id="factor.test",
            version=1,
            status="INVALID_STATUS",
            engine_version="1.0",
            is_online=True,
            is_primary=True,
            created_at="2026-03-18T00:00:00+08:00",
            updated_at="2026-03-18T00:00:00+08:00",
        )
        with pytest.raises(ValueError, match=r"invalid.*version.*status"):
            writer.write_version(record)


class TestWriteRunStatusGuard:
    """write_run() must reject invalid run status strings."""

    def test_accepts_valid_status(self) -> None:
        """Valid DerivedRunStatus values should not raise."""
        writer = _make_writer()
        for status in ("RUNNING", "SUCCESS", "FAILED"):
            record = DerivedRunRecord(
                run_id="run-001",
                derived_id="factor.test",
                version=1,
                mode="incremental",
                trigger="manual",
                request_start="2026-03-01",
                request_end="2026-03-13",
                compute_start="2026-02-10",
                compute_end="2026-03-13",
                source_snapshot_id=None,
                status=status,
                rows_written=0,
                partitions_written=(),
                error_message=None,
                created_at="2026-03-18T00:00:00+08:00",
                started_at="2026-03-18T00:00:00+08:00",
                finished_at=None,
            )
            writer.write_run(record)  # should not raise

    def test_rejects_invalid_status(self) -> None:
        """Invalid status string should raise ValueError."""
        writer = _make_writer()
        record = DerivedRunRecord(
            run_id="run-001",
            derived_id="factor.test",
            version=1,
            mode="incremental",
            trigger="manual",
            request_start="2026-03-01",
            request_end="2026-03-13",
            compute_start="2026-02-10",
            compute_end="2026-03-13",
            source_snapshot_id=None,
            status="BOGUS",
            rows_written=0,
            partitions_written=(),
            error_message=None,
            created_at="2026-03-18T00:00:00+08:00",
            started_at="2026-03-18T00:00:00+08:00",
            finished_at=None,
        )
        with pytest.raises(ValueError, match=r"invalid.*run.*status"):
            writer.write_run(record)


class TestMarkInvalidationStatusGuard:
    """mark_invalidation_status() must reject invalid status strings."""

    def test_accepts_valid_status(self) -> None:
        """Valid CascadeStatus values should not raise."""
        writer = _make_writer()
        for status in ("fresh", "stale", "recomputing", "healed"):
            writer.mark_invalidation_status("inval-001", status)  # should not raise

    def test_rejects_invalid_status(self) -> None:
        """Invalid status string should raise ValueError."""
        writer = _make_writer()
        with pytest.raises(ValueError, match=r"invalid.*invalidation.*status"):
            writer.mark_invalidation_status("inval-001", "BOGUS")


class TestUnitOfWorkExecuteMethods:
    """P1-1: execute_*() methods run SQL without committing."""

    def test_execute_run_does_not_commit(self) -> None:
        """execute_run() should execute SQL but NOT call commit."""
        writer = _make_writer()
        record = DerivedRunRecord(
            run_id="run-001",
            derived_id="factor.test",
            version=1,
            mode="incremental",
            trigger="manual",
            request_start="2026-03-01",
            request_end="2026-03-13",
            compute_start="2026-02-10",
            compute_end="2026-03-13",
            source_snapshot_id=None,
            status="SUCCESS",
            rows_written=0,
            partitions_written=(),
            error_message=None,
            created_at="2026-03-18T00:00:00+08:00",
            started_at="2026-03-18T00:00:00+08:00",
            finished_at="2026-03-18T00:00:00+08:00",
        )
        writer.execute_run(record)

        writer._sqlite_client.execute.assert_called_once()
        assert writer._sqlite_client.commit.call_count == 0

    def test_write_run_commits_after_execute(self) -> None:
        """write_run() should call execute then commit."""
        writer = _make_writer()
        record = DerivedRunRecord(
            run_id="run-001",
            derived_id="factor.test",
            version=1,
            mode="incremental",
            trigger="manual",
            request_start="2026-03-01",
            request_end="2026-03-13",
            compute_start="2026-02-10",
            compute_end="2026-03-13",
            source_snapshot_id=None,
            status="SUCCESS",
            rows_written=0,
            partitions_written=(),
            error_message=None,
            created_at="2026-03-18T00:00:00+08:00",
            started_at="2026-03-18T00:00:00+08:00",
            finished_at="2026-03-18T00:00:00+08:00",
        )
        writer.write_run(record)

        assert writer._sqlite_client.execute.call_count == 1
        assert writer._sqlite_client.commit.call_count == 1

    def test_commit_delegates_to_sqlite_client(self) -> None:
        """Public commit() should delegate to sqlite_client.commit()."""
        writer = _make_writer()
        writer.commit()
        writer._sqlite_client.commit.assert_called_once()

    def test_rollback_delegates_to_sqlite_client(self) -> None:
        """Public rollback() should delegate to sqlite_client.rollback()."""
        writer = _make_writer()
        writer.rollback()
        writer._sqlite_client.rollback.assert_called_once()
