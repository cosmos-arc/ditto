"""Integration tests for IndustryReader and IndustryWriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ditto_datahub.stores.metadata.industry.industry_reader import (
    IndustryReader,
)
from ditto_datahub.stores.metadata.industry.industry_writer import (
    IndustryWriter,
)
from ditto_datahub.stores.metadata.industry.models import IndustryBasic


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def sqlite_client(db_path: Path) -> Any:
    """Create real SQLite client with initialized schema."""
    from ditto_datahub.stores.sqlite_client import SQLiteClient
    from ditto_foundation import SQLitePool

    pool = SQLitePool(str(db_path))
    client = SQLiteClient(pool)

    # Create table
    client.executescript("""
        CREATE TABLE IF NOT EXISTS industry_basic (
            industry_id TEXT PRIMARY KEY,
            industry_name TEXT NOT NULL,
            industry_level TEXT NOT NULL,
            parent_id TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)

    return client


@pytest.fixture
def cache_manager() -> Any:
    """Create real cache manager."""
    from ditto_foundation.cache import DataCache

    return DataCache(enable_metrics=False)


@pytest.fixture
def reader(
    sqlite_client: Any,
    cache_manager: Any,
) -> IndustryReader:
    """Create IndustryReader with real dependencies."""
    return IndustryReader(sqlite_client, cache_manager)


@pytest.fixture
def writer(
    sqlite_client: Any,
    cache_manager: Any,
) -> IndustryWriter:
    """Create IndustryWriter with real dependencies."""
    return IndustryWriter(sqlite_client, cache_manager)


class TestIndustryIntegration:
    """Integration tests for Industry Reader and Writer."""

    def test_write_then_read(
        self,
        writer: IndustryWriter,
        reader: IndustryReader,
    ) -> None:
        """Test writing then reading industry."""
        industry = IndustryBasic(
            industry_id="sw_l1_test",
            industry_name="测试行业",
            industry_level="L1",
        )

        # Write
        writer.register(industry)

        # Read
        result = reader.get_by_id("sw_l1_test")

        assert result is not None
        assert result["industry_id"] == "sw_l1_test"
        assert result["industry_name"] == "测试行业"
        assert result["industry_level"] == "L1"

    def test_write_invalidates_cache(
        self,
        writer: IndustryWriter,
        reader: IndustryReader,
        cache_manager: Any,
    ) -> None:
        """Test that writing invalidates cache."""
        # First read to populate cache
        df1 = reader.get_all()
        initial_count = len(df1)

        # Write new industry
        industry = IndustryBasic(
            industry_id="sw_l1_cache_test",
            industry_name="缓存测试",
            industry_level="L1",
        )
        writer.register(industry)

        # Read again - should see new data
        df2 = reader.get_all()
        assert len(df2) == initial_count + 1

    def test_update_existing_industry(
        self,
        writer: IndustryWriter,
        reader: IndustryReader,
    ) -> None:
        """Test updating existing industry."""
        # Write initial
        industry1 = IndustryBasic(
            industry_id="sw_l1_update",
            industry_name="原始名称",
            industry_level="L1",
        )
        writer.register(industry1)

        # Verify
        result1 = reader.get_by_id("sw_l1_update")
        assert result1["industry_name"] == "原始名称"

        # Update
        industry2 = IndustryBasic(
            industry_id="sw_l1_update",
            industry_name="更新名称",
            industry_level="L1",
        )
        writer.register(industry2)

        # Verify update
        result2 = reader.get_by_id("sw_l1_update")
        assert result2["industry_name"] == "更新名称"

    def test_get_all_filters_correctly(
        self,
        writer: IndustryWriter,
        reader: IndustryReader,
    ) -> None:
        """Test get_all with various filters."""
        # Write test data
        industries = [
            IndustryBasic("sw_l1_01", "行业1", "L1", is_active=True),
            IndustryBasic("sw_l1_02", "行业2", "L1", is_active=False),
            IndustryBasic(
                "sw_l2_01",
                "子行业1",
                "L2",
                parent_id="sw_l1_01",
                is_active=True,
            ),
        ]
        for ind in industries:
            writer.register(ind)

        # Test active filter
        df_active = reader.get_all(is_active=True)
        assert len(df_active) == 2
        assert df_active["is_active"].unique().to_list() == [1]

        # Test level filter (get all L1 regardless of active status)
        df_l1 = reader.get_all(is_active=None, industry_level="L1")
        assert len(df_l1) == 2
        assert df_l1["industry_level"].unique().to_list() == ["L1"]

    def test_cache_behavior(
        self,
        writer: IndustryWriter,
        reader: IndustryReader,
        cache_manager: Any,
    ) -> None:
        """Test cache hit/miss behavior."""
        # First read - cache miss
        df1 = reader.get_all()
        assert len(df1) >= 0

        # Get cache stats after first read
        cache_manager.get_stats()

        # Second read - cache hit (if data was cached)
        df2 = reader.get_all()
        cache_manager.get_stats()

        # Results should be identical
        assert df1.equals(df2)

    def test_get_by_id_not_found(self, reader: IndustryReader) -> None:
        """Test get_by_id with non-existent ID."""
        result = reader.get_by_id("nonexistent_id")
        assert result is None

    def test_inactive_industry(
        self,
        writer: IndustryWriter,
        reader: IndustryReader,
    ) -> None:
        """Test reading inactive industries."""
        # Write active industry first
        active_industry = IndustryBasic(
            industry_id="sw_l1_active",
            industry_name="活跃行业",
            industry_level="L1",
            is_active=True,
        )
        writer.register(active_industry)

        # Write inactive industry
        industry = IndustryBasic(
            industry_id="sw_l1_inactive",
            industry_name="停用行业",
            industry_level="L1",
            is_active=False,
        )
        writer.register(industry)

        # Should not appear in active query
        df_active = reader.get_all(is_active=True)
        assert "sw_l1_inactive" not in df_active["industry_id"].to_list()
        assert "sw_l1_active" in df_active["industry_id"].to_list()

        # Should appear in inactive query
        df_inactive = reader.get_all(is_active=False)
        assert "sw_l1_inactive" in df_inactive["industry_id"].to_list()

        # Should appear in all query (no filter)
        df_all = reader.get_all(is_active=None)
        assert "sw_l1_inactive" in df_all["industry_id"].to_list()
        assert "sw_l1_active" in df_all["industry_id"].to_list()
