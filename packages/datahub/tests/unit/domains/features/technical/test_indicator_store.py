"""Tests for IndicatorStore."""

from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.domains.features.technical.indicator_store import IndicatorStore


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "features" / "technical" / "indicators_narrow"


@pytest.fixture
def indicator_store(temp_data_root: Path) -> IndicatorStore:
    """Create IndicatorStore for testing."""
    return IndicatorStore(temp_data_root)


def test_write_and_read_indicator_data(indicator_store: IndicatorStore) -> None:
    """Test writing and reading indicator data."""
    # Prepare test data
    df = pl.DataFrame(
        {
            "sid": [1, 1, 2, 2],
            "trade_date": [
                "2024-01-02",
                "2024-01-03",
                "2024-01-02",
                "2024-01-03",
            ],
            "indicator_id": [
                "indicator_rsi_14",
                "indicator_rsi_14",
                "indicator_rsi_14",
                "indicator_rsi_14",
            ],
            "indicator_type": ["momentum", "momentum", "momentum", "momentum"],
            "value": [65.5, 68.2, 72.1, 71.5],
            "calc_time": [
                "2024-01-02 15:00:00",
                "2024-01-03 15:00:00",
                "2024-01-02 15:00:00",
                "2024-01-03 15:00:00",
            ],
        }
    )

    # Write data
    result = indicator_store.write(df, year=2024)
    assert result.added == 4
    assert result.updated == 0

    # Read data back
    result_df = indicator_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert len(result_df) == 4
    assert "sid" in result_df.columns
    assert "trade_date" in result_df.columns
    assert "indicator_id" in result_df.columns
    assert "value" in result_df.columns

    # Verify specific values
    result_df_sorted = result_df.sort(["sid", "trade_date"])
    assert result_df_sorted["value"].to_list() == [65.5, 68.2, 72.1, 71.5]


def test_read_filter_by_sid(indicator_store: IndicatorStore) -> None:
    """Test reading with sid filter."""
    # Prepare test data for multiple securities
    df = pl.DataFrame(
        {
            "sid": [1, 2, 3],
            "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "indicator_id": ["indicator_ma_20"] * 3,
            "indicator_type": ["trend"] * 3,
            "value": [10.5, 20.3, 15.7],
            "calc_time": ["2024-01-02 15:00:00"] * 3,
        }
    )

    indicator_store.write(df, year=2024)

    # Read only sid 1 and 2
    result = indicator_store.read(
        sids=[1, 2],
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert len(result) == 2
    assert set(result["sid"].to_list()) == {1, 2}


def test_read_filter_by_indicator_type(indicator_store: IndicatorStore) -> None:
    """Test reading with indicator_type filter."""
    # Prepare test data with different types
    df = pl.DataFrame(
        {
            "sid": [1, 1, 1],
            "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "indicator_id": ["indicator_rsi_14", "indicator_ma_20", "indicator_atr_14"],
            "indicator_type": ["momentum", "trend", "volatility"],
            "value": [65.5, 10.2, 1.5],
            "calc_time": ["2024-01-02 15:00:00"] * 3,
        }
    )

    indicator_store.write(df, year=2024)

    # Read only momentum indicators
    result = indicator_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
        indicator_types=["momentum"],
    )

    assert len(result) == 1
    assert result["indicator_id"][0] == "indicator_rsi_14"


def test_read_preserves_multiple_indicators_per_date(
    indicator_store: IndicatorStore,
) -> None:
    """
    Test that reading preserves all indicators for the same sid/date.

    This is a regression test for the P1 issue where ParquetStoreBase.read()
    deduplicated on ['sid', 'trade_date'], causing data loss when multiple
    indicators exist for the same sid/date combination.
    """
    # Prepare test data: same sid/date, different indicators
    df = pl.DataFrame(
        {
            "sid": [1, 1, 1],
            "trade_date": ["2024-01-02"] * 3,
            "indicator_id": ["indicator_rsi_14", "indicator_ma_20", "indicator_atr_14"],
            "indicator_type": ["momentum", "trend", "volatility"],
            "value": [65.5, 10.2, 1.5],
            "calc_time": ["2024-01-02 15:00:00"] * 3,
        }
    )

    indicator_store.write(df, year=2024)

    # Read all indicators without type filter
    result = indicator_store.read(
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    # Should return all 3 indicators
    assert len(result) == 3
    indicator_ids = set(result["indicator_id"].to_list())
    assert indicator_ids == {"indicator_rsi_14", "indicator_ma_20", "indicator_atr_14"}
