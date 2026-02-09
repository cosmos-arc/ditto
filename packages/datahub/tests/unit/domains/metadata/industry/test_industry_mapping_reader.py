"""Tests for IndustryMappingReader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.industry.industry_mapping_reader import (
    IndustryMappingReader,
)


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

    # Insert test data - stock 1 changes industry over time
    test_data = [
        (1, "801010", "sw", "2024-01-01", "2024-06-01", None),
        (1, "801020", "sw", "2024-06-01", None, "行业调整"),
        (2, "801010", "sw", "2024-01-01", None, None),
        (3, "801010", "sw", "2024-01-01", "2024-03-01", None),
        (3, "801020", "sw", "2024-03-01", None, None),
    ]
    conn = pool.get_connection()
    insert_sql = (
        "INSERT INTO industry_mapping "
        "(instrument_id, industry_id, source, effective_from, "
        "effective_to, entry_reason) "
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
def reader(mock_client: Any, mock_cache: Any) -> IndustryMappingReader:
    """Create IndustryMappingReader instance."""
    return IndustryMappingReader(mock_client, mock_cache)


class TestIndustryMappingReader:
    """Test suite for IndustryMappingReader."""

    def test_get_stock_industry_current(self, reader: IndustryMappingReader) -> None:
        """Test get_stock_industry returns current mapping."""
        result = reader.get_stock_industry(1)

        assert result is not None
        assert result["instrument_id"] == 1
        assert result["industry_id"] == "801020"  # Latest mapping
        assert result["source"] == "sw"
        assert result["effective_to"] is None

    def test_get_stock_industry_not_found(self, reader: IndustryMappingReader) -> None:
        """Test get_stock_industry with non-existent stock."""
        result = reader.get_stock_industry(999)
        assert result is None

    def test_get_stock_industry_pit_historical(
        self,
        reader: IndustryMappingReader,
    ) -> None:
        """Test get_stock_industry with historical asof date."""
        # Query before the change - should get 801010
        result = reader.get_stock_industry(1, asof="2024-03-01")
        assert result is not None
        assert result["industry_id"] == "801010"

    def test_get_stock_industry_pit_after_change(
        self,
        reader: IndustryMappingReader,
    ) -> None:
        """Test get_stock_industry with asof after industry change."""
        # Query after the change - should get 801020
        result = reader.get_stock_industry(1, asof="2024-07-01")
        assert result is not None
        assert result["industry_id"] == "801020"

    def test_get_stocks_current(self, reader: IndustryMappingReader) -> None:
        """Test get_stocks returns current industry members."""
        stocks = reader.get_stocks("801010")
        assert set(stocks) == {2}  # Only stock 2 is currently in 801010

    def test_get_stocks_pit(self, reader: IndustryMappingReader) -> None:
        """Test get_stocks with Point-in-Time query."""
        # Query in February 2024 - before stock 1 moved and stock 3 left
        stocks = reader.get_stocks("801010", asof="2024-02-01")
        assert set(stocks) == {1, 2, 3}

        # Query in April 2024 - after stock 3 left but before stock 1 moved
        stocks = reader.get_stocks("801010", asof="2024-04-01")
        assert set(stocks) == {1, 2}

    def test_get_stocks_empty_industry(self, reader: IndustryMappingReader) -> None:
        """Test get_stocks with industry that has no members."""
        stocks = reader.get_stocks("nonexistent")
        assert stocks == []

    def test_get_stock_industry_multiple_mappings(
        self,
        reader: IndustryMappingReader,
    ) -> None:
        """Test stock with multiple industry changes over time."""
        # Stock 3: 801010 -> 801020
        result_mar = reader.get_stock_industry(3, asof="2024-02-01")
        assert result_mar["industry_id"] == "801010"

        result_apr = reader.get_stock_industry(3, asof="2024-04-01")
        assert result_apr["industry_id"] == "801020"

        result_current = reader.get_stock_industry(3)
        assert result_current["industry_id"] == "801020"
