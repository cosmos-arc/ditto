"""Tests for FactorStore."""

from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.domains.factors.factor_store import FactorStore


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "factors" / "factors_narrow"


@pytest.fixture
def factor_store(temp_data_root: Path) -> FactorStore:
    """Create FactorStore for testing."""
    return FactorStore(temp_data_root)


def test_write_and_read_factor_data(factor_store: FactorStore) -> None:
    """Test writing and reading factor data."""
    # Prepare test data with PIT columns
    df = pl.DataFrame(
        {
            "sid": [1, 1, 2, 2],
            "trade_date": [
                "2024-01-02",
                "2024-01-03",
                "2024-01-02",
                "2024-01-03",
            ],
            "factor_id": ["factor_momentum_12m"] * 4,
            "factor_class": ["technical"] * 4,
            "factor_family": ["momentum"] * 4,
            "exposure": [0.5, 0.6, 0.3, 0.4],
            "raw_value": [0.15, 0.18, 0.08, 0.12],
            "effective_from": ["2024-01-02"] * 4,
            "effective_to": [None] * 4,
        }
    )

    # Write data
    result = factor_store.write(df, year=2024)
    assert result.added == 4

    # Read data back
    result_df = factor_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert len(result_df) == 4
    assert "sid" in result_df.columns
    assert "trade_date" in result_df.columns
    assert "factor_id" in result_df.columns
    assert "exposure" in result_df.columns
    assert "effective_from" in result_df.columns
    assert "effective_to" in result_df.columns


def test_read_with_as_of_date_pit_query(factor_store: FactorStore) -> None:
    """Test PIT query with as_of_date parameter."""
    # Write initial data
    df_v1 = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "factor_id": ["factor_momentum_12m"] * 2,
            "factor_class": ["technical"] * 2,
            "factor_family": ["momentum"] * 2,
            "exposure": [0.5, 0.6],
            "raw_value": [0.15, 0.18],
            "effective_from": ["2024-01-02"] * 2,
            "effective_to": ["2024-01-10"] * 2,  # Version 1 valid until 1/10
        }
    )

    # Write revised data
    df_v2 = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "factor_id": ["factor_momentum_12m"] * 2,
            "factor_class": ["technical"] * 2,
            "factor_family": ["momentum"] * 2,
            "exposure": [0.55, 0.65],  # Revised values
            "raw_value": [0.16, 0.19],
            "effective_from": ["2024-01-10"] * 2,  # Version 2 starts 1/10
            "effective_to": [None] * 2,  # Current version
        }
    )

    # Combine and write (simulating two versions of same data)
    df_combined = pl.concat([df_v1, df_v2])
    factor_store.write(df_combined, year=2024)

    # Query as of 2024-01-05 (should get version 1)
    result_v1 = factor_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
        as_of_date="2024-01-05",
    )

    assert len(result_v1) == 2
    # Should get version 1 values
    # Use date literal for comparison since trade_date is converted to date type
    row_v1 = result_v1.filter(pl.col("trade_date") == pl.date(2024, 1, 2))
    assert len(row_v1) == 1
    assert row_v1["exposure"][0] == 0.5

    # Query as of 2024-01-15 (should get version 2)
    result_v2 = factor_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
        as_of_date="2024-01-15",
    )

    assert len(result_v2) == 2
    # Should get version 2 values
    row_v2 = result_v2.filter(pl.col("trade_date") == pl.date(2024, 1, 2))
    assert len(row_v2) == 1
    assert row_v2["exposure"][0] == 0.55


def test_write_validates_required_columns(factor_store: FactorStore) -> None:
    """Test that write validates required columns."""
    # Missing 'exposure' column
    df_invalid = pl.DataFrame(
        {
            "sid": [1],
            "trade_date": ["2024-01-02"],
            "factor_id": ["factor_momentum_12m"],
            "factor_class": ["technical"],
            "factor_family": ["momentum"],
            # 'exposure' is missing
            "raw_value": [0.15],
            "effective_from": ["2024-01-02"],
        }
    )

    with pytest.raises(ValueError, match="Missing required columns"):
        factor_store.write(df_invalid, year=2024)


def test_read_with_sid_filter(factor_store: FactorStore) -> None:
    """Test reading with sid filter."""
    # Write data for multiple securities
    df = pl.DataFrame(
        {
            "sid": [1, 1, 2, 2, 3, 3],
            "trade_date": [
                "2024-01-02",
                "2024-01-03",
                "2024-01-02",
                "2024-01-03",
                "2024-01-02",
                "2024-01-03",
            ],
            "factor_id": ["factor_momentum_12m"] * 6,
            "factor_class": ["technical"] * 6,
            "factor_family": ["momentum"] * 6,
            "exposure": [0.5, 0.6, 0.3, 0.4, 0.7, 0.8],
            "raw_value": [0.15, 0.18, 0.08, 0.12, 0.20, 0.25],
            "effective_from": ["2024-01-02"] * 6,
            "effective_to": [None] * 6,
        }
    )

    factor_store.write(df, year=2024)

    # Read only sid 1 and 2
    result = factor_store.read(
        sids=[1, 2],
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert len(result) == 4
    assert set(result["sid"].to_list()) == {1, 2}


def test_write_with_duplicate_handling(factor_store: FactorStore) -> None:
    """Test writing with duplicate handling strategies."""
    from ditto_datahub.models import OnDuplicate

    # Write initial data
    df_v1 = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "factor_id": ["factor_momentum_12m"] * 2,
            "factor_class": ["technical"] * 2,
            "factor_family": ["momentum"] * 2,
            "exposure": [0.5, 0.6],
            "raw_value": [0.15, 0.18],
            "effective_from": ["2024-01-02"] * 2,
            "effective_to": [None] * 2,
        }
    )

    result_v1 = factor_store.write(df_v1, year=2024)
    assert result_v1.added == 2

    # Try to write overlapping data with ERROR strategy (should fail)
    df_overlap = pl.DataFrame(
        {
            "sid": [1],
            "trade_date": ["2024-01-02"],
            "factor_id": ["factor_momentum_12m"],
            "factor_class": ["technical"],
            "factor_family": ["momentum"],
            "exposure": [0.55],
            "raw_value": [0.16],
            "effective_from": ["2024-01-02"],  # Same key
            "effective_to": [None],
        }
    )

    with pytest.raises(ValueError, match="Duplicate data"):
        factor_store.write(df_overlap, year=2024, on_duplicate=OnDuplicate.ERROR)

    # Write with KEEP_LAST strategy (should succeed)
    result_v2 = factor_store.write(
        df_overlap, year=2024, on_duplicate=OnDuplicate.KEEP_LAST
    )
    assert result_v2.added == 0
    assert result_v2.updated == 1


def test_read_empty_store(factor_store: FactorStore) -> None:
    """Test reading from empty store."""
    result = factor_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert result.is_empty()


def test_get_metadata_methods(factor_store: FactorStore) -> None:
    """Test metadata methods."""
    # Initially empty
    assert factor_store.get_years() == []

    # Write data
    df = pl.DataFrame(
        {
            "sid": [1],
            "trade_date": ["2024-01-02"],
            "factor_id": ["factor_momentum_12m"],
            "factor_class": ["technical"],
            "factor_family": ["momentum"],
            "exposure": [0.5],
            "raw_value": [0.15],
            "effective_from": ["2024-01-02"],
            "effective_to": [None],
        }
    )

    factor_store.write(df, year=2024)

    # Check years
    assert factor_store.get_years() == [2024]

    # Check checksum
    checksum = factor_store.get_checksum(2024)
    assert checksum != ""

    # Check date range
    start, end = factor_store.get_date_range()
    assert start == "2024-01-02"
    assert end == "2024-01-02"

    # Check sids
    sids = factor_store.list_sids()
    assert sids == [1]

    # Check count
    count = factor_store.count()
    assert count == 1


def test_delete_year_partition(factor_store: FactorStore) -> None:
    """Test deleting a year partition."""
    # Write data
    df = pl.DataFrame(
        {
            "sid": [1],
            "trade_date": ["2024-01-02"],
            "factor_id": ["factor_momentum_12m"],
            "factor_class": ["technical"],
            "factor_family": ["momentum"],
            "exposure": [0.5],
            "raw_value": [0.15],
            "effective_from": ["2024-01-02"],
            "effective_to": [None],
        }
    )

    factor_store.write(df, year=2024)

    # Verify data exists
    assert factor_store.get_years() == [2024]

    # Delete
    deleted = factor_store.delete(2024)
    assert deleted is True

    # Verify data is gone
    assert factor_store.get_years() == []

    # Delete again should return False
    deleted_again = factor_store.delete(2024)
    assert deleted_again is False
