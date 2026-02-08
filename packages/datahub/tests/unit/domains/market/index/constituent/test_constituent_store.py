"""Tests for IndexConstituentStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.stores.market.index.constituent import IndexConstituentStore


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def store(data_root: Path) -> IndexConstituentStore:
    """Create IndexConstituentStore instance."""
    return IndexConstituentStore(data_root)


@pytest.fixture
def sample_constituents_df() -> pl.DataFrame:
    """Create sample index constituents DataFrame."""
    return pl.DataFrame(
        {
            "index_instrument_id": [1600001, 1600001, 1600001, 1600001, 1600002],
            "constituent_instrument_id": [1, 2, 3, 4, 1],
            "effective_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
                date(2024, 1, 1),
                date(2024, 1, 1),
                date(2024, 1, 1),
            ],
            "weight": [0.25, 0.25, 0.25, 0.25, 1.0],
        }
    )


@pytest.fixture
def sample_constituents_with_changes() -> pl.DataFrame:
    """Create sample index constituents with changes over time."""
    return pl.DataFrame(
        {
            "index_instrument_id": [
                1600001,
                1600001,
                1600001,
                1600001,
                1600001,
                1600001,
            ],
            "constituent_instrument_id": [1, 2, 3, 4, 2, 5],
            "effective_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
                date(2024, 1, 1),
                date(2024, 1, 1),
                date(2024, 2, 1),  # Stock 2 removed
                date(2024, 2, 1),  # Stock 5 added
            ],
            "weight": [0.25, 0.25, 0.25, 0.25, 0.0, 0.25],
        }
    )


class TestIndexConstituentStore:
    """Test suite for IndexConstituentStore."""

    # ============ init tests ============

    def test_init_creates_directory(
        self, store: IndexConstituentStore, tmp_path: Path
    ) -> None:
        """Test that initialization creates the database directory."""
        db_dir = tmp_path / "data" / "market" / "index"
        assert db_dir.exists()

    def test_db_path(self, store: IndexConstituentStore, tmp_path: Path) -> None:
        """Test that db_path is correct."""
        expected_path = tmp_path / "data" / "market" / "index" / "constituent.db"
        assert store.db_path == expected_path

    # ============ write tests ============

    def test_write_creates_table(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test write creates the table."""
        store.write(sample_constituents_df)
        # Table should exist now
        result = store.read()
        assert len(result) == 5

    def test_write_empty_df(self, store: IndexConstituentStore) -> None:
        """Test write with empty DataFrame."""
        empty_df = pl.DataFrame(
            {
                "index_instrument_id": [],
                "constituent_instrument_id": [],
                "effective_date": [],
                "weight": [],
            }
        )
        result = store.write(empty_df)
        assert result.added == 0
        assert result.updated == 0

    def test_write_merge_with_existing(
        self,
        store: IndexConstituentStore,
        sample_constituents_df: pl.DataFrame,
    ) -> None:
        """Test write merges with existing data."""
        # Write initial data
        store.write(sample_constituents_df)

        # Write new data
        new_data = pl.DataFrame(
            {
                "index_instrument_id": [1600001, 1600002],
                "constituent_instrument_id": [5, 2],
                "effective_date": [date(2024, 1, 1), date(2024, 1, 1)],
                "weight": [0.20, 1.0],
            }
        )
        result = store.write(new_data)

        assert result.added >= 0
        assert result.is_merge is True

    # ============ get tests ============

    def test_get_empty(self, store: IndexConstituentStore) -> None:
        """Test get with no data."""
        result = store.get(index_instrument_id=1600001, asof=date(2024, 1, 1))
        assert len(result) == 0

    def test_get_simple(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test get returns constituents for an index as of a date."""
        store.write(sample_constituents_df)
        result = store.get(index_instrument_id=1600001, asof=date(2024, 1, 1))
        assert len(result) == 4
        assert set(result["constituent_instrument_id"].to_list()) == {1, 2, 3, 4}

    def test_get_with_date_before_effective(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test get with date before effective_date returns empty."""
        store.write(sample_constituents_df)
        result = store.get(index_instrument_id=1600001, asof=date(2023, 12, 31))
        assert len(result) == 0

    def test_get_pit(
        self,
        store: IndexConstituentStore,
        sample_constituents_with_changes: pl.DataFrame,
    ) -> None:
        """Test get with Point-in-Time logic."""
        store.write(sample_constituents_with_changes)

        # Before change
        result = store.get(index_instrument_id=1600001, asof=date(2024, 1, 15))
        assert len(result) == 4
        assert set(result["constituent_instrument_id"].to_list()) == {1, 2, 3, 4}

        # After change (stock 2 removed, stock 5 added)
        result = store.get(index_instrument_id=1600001, asof=date(2024, 2, 15))
        # Should have stocks 1, 3, 4, 5 (stock 2 removed with weight 0)
        constituents = result.filter(pl.col("weight") > 0)
        assert set(constituents["constituent_instrument_id"].to_list()) == {1, 3, 4, 5}

    def test_get_multiple_indices(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test get returns correct constituents for different indices."""
        store.write(sample_constituents_df)

        result1 = store.get(index_instrument_id=1600001, asof=date(2024, 1, 1))
        assert len(result1) == 4

        result2 = store.get(index_instrument_id=1600002, asof=date(2024, 1, 1))
        assert len(result2) == 1
        assert result2["constituent_instrument_id"][0] == 1

    def test_get_nonexistent_index(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test get with non-existent index."""
        store.write(sample_constituents_df)
        result = store.get(index_instrument_id=1699999, asof=date(2024, 1, 1))
        assert len(result) == 0

    # ============ read tests ============

    def test_read_all(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test read returns all data."""
        store.write(sample_constituents_df)
        result = store.read()
        assert len(result) == 5

    def test_read_filter_by_index_sid(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test read filtered by index_instrument_id."""
        store.write(sample_constituents_df)
        result = store.read(index_instrument_ids=[1600001])
        assert len(result) == 4
        assert all(result["index_instrument_id"] == 1600001)

    # ============ delete tests ============

    def test_delete_by_index_sid(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test delete removes constituents for an index."""
        store.write(sample_constituents_df)

        deleted_count = store.delete(index_instrument_ids=[1600001])
        assert deleted_count == 4

        # Verify deletion
        result = store.read()
        assert len(result) == 1  # Only 1600002 remains
        assert result["index_instrument_id"][0] == 1600002

    def test_delete_by_date_range(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test delete with date range."""
        store.write(sample_constituents_df)

        deleted_count = store.delete(
            index_instrument_ids=[1600001],
            start_date="2024-01-01",
            end_date="2024-01-01",
        )
        assert deleted_count == 4

    # ============ count tests ============

    def test_count_empty(self, store: IndexConstituentStore) -> None:
        """Test count with no data."""
        count = store.count()
        assert count == 0

    def test_count(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test count returns total records."""
        store.write(sample_constituents_df)
        count = store.count()
        assert count == 5

    def test_count_filter_by_index(
        self, store: IndexConstituentStore, sample_constituents_df: pl.DataFrame
    ) -> None:
        """Test count filtered by index."""
        store.write(sample_constituents_df)
        count = store.count(index_instrument_ids=[1600001])
        assert count == 4
