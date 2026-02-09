"""Tests for IndustryReader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import pytest
from ditto_datahub.stores.metadata.industry.industry_reader import (
    IndustryReader,
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
        CREATE TABLE industry_basic (
            industry_id TEXT PRIMARY KEY,
            industry_name TEXT NOT NULL,
            industry_level TEXT NOT NULL,
            parent_id TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Insert test data
    test_data = [
        ("sw_l1_01", "申万一级行业01", "L1", None, 1),
        ("sw_l1_02", "申万一级行业02", "L1", None, 1),
        ("sw_l2_0101", "申万二级行业0101", "L2", "sw_l1_01", 1),
        ("sw_l1_03", "申万一级行业03", "L1", None, 0),  # inactive
    ]
    conn = pool.get_connection()
    insert_sql = (
        "INSERT INTO industry_basic "
        "(industry_id, industry_name, industry_level, parent_id, is_active) "
        "VALUES (?, ?, ?, ?, ?)"
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
def reader(mock_client: Any, mock_cache: Any) -> IndustryReader:
    """Create IndustryReader instance."""
    return IndustryReader(mock_client, mock_cache)


class TestIndustryReader:
    """Test suite for IndustryReader."""

    def test_get_all_returns_dataframe(self, reader: IndustryReader) -> None:
        """Test get_all returns polars DataFrame."""
        df = reader.get_all()
        assert isinstance(df, pl.DataFrame)

    def test_get_all_with_active_filter(self, reader: IndustryReader) -> None:
        """Test get_all with is_active filter."""
        df = reader.get_all(is_active=True)
        assert len(df) == 3  # Only active industries

        df_inactive = reader.get_all(is_active=False)
        assert len(df_inactive) == 1  # Only inactive industry

    def test_get_all_with_level_filter(self, reader: IndustryReader) -> None:
        """Test get_all with industry_level filter."""
        df = reader.get_all(industry_level="L1")
        assert len(df) == 2
        assert df["industry_level"].unique().to_list() == ["L1"]

    def test_get_all_cache_hit(
        self,
        reader: IndustryReader,
        mock_cache: Any,
    ) -> None:
        """Test get_all returns cached data when available."""
        from unittest.mock import Mock

        cached_df = pl.DataFrame({"industry_id": ["cached"]})
        mock_cache.get = Mock(return_value=cached_df)

        df = reader.get_all()

        assert df.equals(cached_df)
        mock_cache.get.assert_called_once()

    def test_get_all_cache_miss_set_cache(
        self,
        reader: IndustryReader,
        mock_cache: Any,
    ) -> None:
        """Test get_all sets cache on miss."""
        df = reader.get_all()

        assert len(df) > 0
        mock_cache.set.assert_called_once()

    def test_get_by_id_found(self, reader: IndustryReader) -> None:
        """Test get_by_id returns industry when found."""
        result = reader.get_by_id("sw_l1_01")

        assert result is not None
        assert result["industry_id"] == "sw_l1_01"
        assert result["industry_name"] == "申万一级行业01"

    def test_get_by_id_not_found(self, reader: IndustryReader) -> None:
        """Test get_by_id returns None when not found."""
        result = reader.get_by_id("nonexistent")
        assert result is None

    def test_get_all_empty_database(
        self,
        mock_client: Any,
        mock_cache: Any,
    ) -> None:
        """Test get_all with empty database."""
        # Create reader with empty database
        from ditto_foundation import SQLitePool

        empty_pool = SQLitePool(":memory:")
        empty_pool.get_connection().execute("""
            CREATE TABLE industry_basic (
                industry_id TEXT PRIMARY KEY,
                industry_name TEXT NOT NULL,
                industry_level TEXT NOT NULL,
                parent_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)

        from unittest.mock import Mock

        empty_client = Mock()
        empty_client.fetchall = Mock(
            side_effect=lambda sql, params: _fetchall_impl(
                empty_pool,
                sql,
                params,
            ),
        )

        empty_reader = IndustryReader(empty_client, mock_cache)
        df = empty_reader.get_all()

        assert isinstance(df, pl.DataFrame)
        assert len(df) == 0
