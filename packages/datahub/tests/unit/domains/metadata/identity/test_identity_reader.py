"""Tests for IdentityReader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.identity.identity_reader import IdentityReader


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

    # Insert test data - stock 1 changes ticker over time
    test_data = [
        (1, "tdx", "000001.SZ", "2024-01-01", "2024-06-01", 1),
        (1, "tdx", "000001.SZ", "2024-06-01", None, 1),
        (2, "tdx", "000002.SZ", "2024-01-01", None, 1),
        (3, "tdx", "600000.SH", "2024-01-01", None, 1),
    ]
    conn = pool.get_connection()
    insert_sql = (
        "INSERT INTO identity_mapping "
        "(instrument_id, source, source_ticker, effective_from, "
        "effective_to, is_primary) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    for row in test_data:
        conn.execute(insert_sql, row)
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
def reader(mock_client: Any, mock_cache: Any) -> IdentityReader:
    """Create IdentityReader instance."""
    return IdentityReader(mock_client, mock_cache)


class TestIdentityReader:
    """Test suite for IdentityReader."""

    def test_resolve_instrument_id_current(self, reader: IdentityReader) -> None:
        """Test resolve_instrument_id returns current mapping."""
        result = reader.resolve_instrument_id("000001.SZ", "tdx")

        assert result == 1

    def test_resolve_instrument_id_not_found(self, reader: IdentityReader) -> None:
        """Test resolve_instrument_id with non-existent ticker."""
        result = reader.resolve_instrument_id("999999.SZ", "tdx")
        assert result is None

    def test_resolve_instrument_id_pit_historical(
        self,
        reader: IdentityReader,
    ) -> None:
        """Test resolve_instrument_id with historical asof date."""
        # Query before any change - should return 1
        result = reader.resolve_instrument_id("000001.SZ", "tdx", asof="2024-03-01")
        assert result == 1

    def test_resolve_instrument_id_pit_after_change(
        self,
        reader: IdentityReader,
    ) -> None:
        """Test resolve_instrument_id with asof after ticker change."""
        # Query after the change - should still return 1
        # (same ticker was re-registered with new effective_from)
        result = reader.resolve_instrument_id("000001.SZ", "tdx", asof="2024-07-01")
        assert result == 1

    def test_get_source_ticker_current(self, reader: IdentityReader) -> None:
        """Test get_source_ticker returns current mapping."""
        result = reader.get_source_ticker(1, "tdx")

        assert result == "000001.SZ"

    def test_get_source_ticker_not_found(self, reader: IdentityReader) -> None:
        """Test get_source_ticker with non-existent instrument_id."""
        result = reader.get_source_ticker(999, "tdx")
        assert result is None

    def test_get_source_ticker_pit(self, reader: IdentityReader) -> None:
        """Test get_source_ticker with Point-in-Time query."""
        # Stock 1 had same ticker throughout
        result = reader.get_source_ticker(1, "tdx", asof="2024-03-01")
        assert result == "000001.SZ"

        result_current = reader.get_source_ticker(1, "tdx")
        assert result_current == "000001.SZ"

    def test_resolve_instrument_ids_batch(self, reader: IdentityReader) -> None:
        """Test batch resolution of multiple tickers."""
        tickers = ["000001.SZ", "000002.SZ", "999999.SZ"]
        result = reader.resolve_instrument_ids_batch(tickers, "tdx")

        assert result["000001.SZ"] == 1
        assert result["000002.SZ"] == 2
        assert "999999.SZ" not in result  # Not found should be excluded

    def test_resolve_instrument_ids_batch_empty(self, reader: IdentityReader) -> None:
        """Test batch resolution with empty list."""
        result = reader.resolve_instrument_ids_batch([], "tdx")
        assert result == {}

    def test_resolve_instrument_ids_batch_pit(self, reader: IdentityReader) -> None:
        """Test batch resolution with PIT query."""
        tickers = ["000001.SZ", "000002.SZ"]
        result = reader.resolve_instrument_ids_batch(
            tickers,
            "tdx",
            asof="2024-03-01",
        )

        assert result["000001.SZ"] == 1
        assert result["000002.SZ"] == 2
