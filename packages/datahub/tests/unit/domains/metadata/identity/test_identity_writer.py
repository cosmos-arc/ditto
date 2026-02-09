"""Tests for IdentityWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.identity.identity_writer import IdentityWriter


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def mock_client(db_path: Path) -> Any:
    """Create mock SQLite client with test data."""
    from unittest.mock import Mock

    from ditto_foundation import SQLitePool

    # Create real pool with in-memory database
    pool = SQLitePool(":memory:")

    # Initialize schema
    client = Mock()
    client.execute = Mock(
        side_effect=lambda sql, params: pool.get_connection().execute(
            sql,
            params or [],
        ),
    )
    client.fetchone = Mock(
        side_effect=lambda sql, params: _fetchone_impl(
            pool,
            sql,
            params,
        ),
    )
    client.fetchall = Mock(
        side_effect=lambda sql, params: _fetchall_impl(
            pool,
            sql,
            params,
        ),
    )
    client.commit = Mock(side_effect=lambda: pool.get_connection().commit())

    # Create table
    pool.get_connection().execute("""
        CREATE TABLE identity_mapping (
            instrument_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_ticker TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            is_primary INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (source, source_ticker, effective_from)
        )
    """)

    return client


def _fetchone_impl(
    pool: Any,
    sql: str,
    params: Any,
) -> dict[str, Any] | None:
    """Implementation for mock fetchone."""
    cursor = pool.get_connection().execute(sql, params or [])
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row, strict=True))
    return None


def _fetchall_impl(
    pool: Any,
    sql: str,
    params: Any,
) -> list[dict[str, Any]]:
    """Implementation for mock fetchall."""
    cursor = pool.get_connection().execute(sql, params or [])
    rows = cursor.fetchall()
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in rows]


@pytest.fixture
def mock_cache() -> Any:
    """Create mock cache manager."""
    from unittest.mock import Mock

    cache = Mock()
    cache.get = Mock(return_value=None)
    cache.set = Mock()
    cache.invalidate = Mock()
    cache.invalidate_pattern = Mock(return_value=0)
    return cache


@pytest.fixture
def writer(mock_client: Any, mock_cache: Any) -> IdentityWriter:
    """Create IdentityWriter instance."""
    return IdentityWriter(mock_client, mock_cache)


class TestIdentityWriter:
    """Test suite for IdentityWriter."""

    def test_register_inserts_record(
        self,
        writer: IdentityWriter,
        mock_client: Any,
    ) -> None:
        """Test register inserts new mapping."""
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
        )

        mock_client.execute.assert_called_once()
        mock_client.commit.assert_called_once()

    def test_register_with_is_primary_true(
        self,
        writer: IdentityWriter,
        mock_client: Any,
    ) -> None:
        """Test register with is_primary=True."""
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
            is_primary=True,
        )

        call_args = mock_client.execute.call_args
        params = (
            call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", [])
        )

        # is_primary should be converted to 1
        assert params[4] == 1

    def test_register_with_is_primary_false(
        self,
        writer: IdentityWriter,
        mock_client: Any,
    ) -> None:
        """Test register with is_primary=False."""
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
            is_primary=False,
        )

        call_args = mock_client.execute.call_args
        params = (
            call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", [])
        )

        # is_primary should be converted to 0
        assert params[4] == 0

    def test_register_commits_transaction(
        self,
        writer: IdentityWriter,
        mock_client: Any,
    ) -> None:
        """Test register commits after insert."""
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
        )

        mock_client.commit.assert_called_once()

    def test_register_invalidates_cache(
        self,
        writer: IdentityWriter,
        mock_cache: Any,
    ) -> None:
        """Test register invalidates relevant cache."""
        writer.register(
            instrument_id=1,
            source_ticker="000001.SZ",
            source="tdx",
            effective_from="2024-01-01",
        )

        mock_cache.invalidate_pattern.assert_called_once_with("identity:*")

    def test_register_handles_database_error(
        self,
        writer: IdentityWriter,
        mock_client: Any,
    ) -> None:
        """Test register propagates database errors."""
        # Make execute raise an exception
        mock_client.execute.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            writer.register(
                instrument_id=1,
                source_ticker="000001.SZ",
                source="tdx",
                effective_from="2024-01-01",
            )

        # Commit should not be called on error
        assert mock_client.commit.call_count == 0
