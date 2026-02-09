"""Tests for IndustryMappingWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.industry.industry_mapping_writer import (
    IndustryMappingWriter,
)
from ditto_datahub.stores.metadata.industry.models import IndustryMapping


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
        CREATE TABLE industry_mapping (
            instrument_id INTEGER NOT NULL,
            industry_id TEXT NOT NULL,
            source TEXT DEFAULT 'sw',
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            entry_reason TEXT,
            PRIMARY KEY (instrument_id, effective_from)
        )
    """)

    # Insert existing mapping for stock 1
    conn = pool.get_connection()
    insert_sql = (
        "INSERT INTO industry_mapping "
        "(instrument_id, industry_id, source, effective_from, effective_to) "
        "VALUES (?, ?, 'sw', ?, NULL)"
    )
    conn.execute(insert_sql, (1, "801010", "2024-01-01"))
    conn.commit()

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
def writer(mock_client: Any, mock_cache: Any) -> IndustryMappingWriter:
    """Create IndustryMappingWriter instance."""
    return IndustryMappingWriter(mock_client, mock_cache)


class TestIndustryMappingWriter:
    """Test suite for IndustryMappingWriter."""

    def test_update_mapping_inserts_new_record(
        self,
        writer: IndustryMappingWriter,
        mock_client: Any,
    ) -> None:
        """Test update_mapping inserts new mapping."""
        mapping = IndustryMapping(
            instrument_id=2,
            industry_id="801020",
            effective_from="2024-03-01",
            entry_reason="首次入选",
        )

        writer.update_mapping(mapping)

        # Verify execute was called twice (invalidate old + insert new)
        assert mock_client.execute.call_count == 2
        mock_client.commit.assert_called_once()

    def test_update_mapping_invalidates_old_record(
        self,
        writer: IndustryMappingWriter,
        mock_client: Any,
    ) -> None:
        """Test update_mapping invalidates previous mapping."""
        mapping = IndustryMapping(
            instrument_id=1,
            industry_id="801020",
            effective_from="2024-06-01",
            entry_reason="行业调整",
        )

        writer.update_mapping(mapping)

        # First call should be UPDATE to invalidate old record
        first_call_args = mock_client.execute.call_args_list[0]
        sql = first_call_args[0][0]
        params = first_call_args[0][1]

        assert "UPDATE industry_mapping" in sql
        assert "SET effective_to = ?" in sql
        assert params[1] == 1  # instrument_id

    def test_update_mapping_commits_transaction(
        self,
        writer: IndustryMappingWriter,
        mock_client: Any,
    ) -> None:
        """Test update_mapping commits after both operations."""
        mapping = IndustryMapping(
            instrument_id=1,
            industry_id="801020",
            effective_from="2024-06-01",
        )

        writer.update_mapping(mapping)

        mock_client.commit.assert_called_once()

    def test_update_mapping_invalidates_cache(
        self,
        writer: IndustryMappingWriter,
        mock_cache: Any,
    ) -> None:
        """Test update_mapping invalidates relevant cache."""
        mapping = IndustryMapping(
            instrument_id=1,
            industry_id="801020",
            effective_from="2024-06-01",
        )

        writer.update_mapping(mapping)

        mock_cache.invalidate_pattern.assert_called_once_with("industry:mapping:*")

    def test_update_mapping_with_entry_reason(
        self,
        writer: IndustryMappingWriter,
        mock_client: Any,
    ) -> None:
        """Test update_mapping includes entry_reason."""
        mapping = IndustryMapping(
            instrument_id=1,
            industry_id="801020",
            effective_from="2024-06-01",
            entry_reason="行业调整",
        )

        writer.update_mapping(mapping)

        # Verify execute was called twice (UPDATE + INSERT)
        assert mock_client.execute.call_count == 2

        # Verify that INSERT contains entry_reason column
        # Check all SQL calls for the INSERT statement with entry_reason
        found_insert_with_entry_reason = False
        for call in mock_client.execute.call_args_list:
            args = call[0]  # positional args
            if len(args) >= 1:
                sql = args[0]
                if "INSERT INTO industry_mapping" in sql and "entry_reason" in sql:
                    found_insert_with_entry_reason = True
                    break

        assert found_insert_with_entry_reason, (
            "INSERT statement with entry_reason not found"
        )

    def test_update_mapping_without_entry_reason(
        self,
        writer: IndustryMappingWriter,
        mock_client: Any,
    ) -> None:
        """Test update_mapping works without entry_reason."""
        mapping = IndustryMapping(
            instrument_id=2,
            industry_id="801020",
            effective_from="2024-06-01",
            # entry_reason defaults to None
        )

        writer.update_mapping(mapping)

        # Verify execute was called (no error should occur)
        assert mock_client.execute.call_count == 2
