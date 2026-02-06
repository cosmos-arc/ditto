"""Tests for FeatureService."""

from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.domains.features.feature_service import (
    FeatureQuery,
    FeatureService,
)
from ditto_datahub.domains.features.technical import (
    IndicatorMetadataStore,
    IndicatorStore,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    """Create temporary data root."""
    return tmp_path / "features"


@pytest.fixture
def feature_service(
    temp_data_root: Path,
    sqlite_client: SQLiteClient,
) -> FeatureService:
    """
    Create FeatureService for testing.

    Uses the sqlite_client fixture from conftest.py (memory database).
    """
    indicator_store = IndicatorStore(temp_data_root / "technical" / "indicators_narrow")
    metadata_store = IndicatorMetadataStore(sqlite_client)
    return FeatureService(indicator_store, metadata_store)


def test_get_indicators_enriches_with_metadata(feature_service: FeatureService) -> None:
    """Test that get_indicators enriches data with metadata."""
    # Setup: Register indicator metadata
    feature_service._metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        indicator_type="momentum",
        description="14-day RSI",
        formula="RSI",
        parameters="{}",
    )

    # Setup: Write indicator data
    df = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "indicator_id": ["indicator_rsi_14", "indicator_rsi_14"],
            "indicator_type": ["momentum", "momentum"],
            "value": [65.5, 68.2],
            "calc_time": ["2024-01-02 15:00:00", "2024-01-03 15:00:00"],
        }
    )
    feature_service._indicator_store.write(df, year=2024)

    # Execute: Query indicators
    query = FeatureQuery(
        indicators=["indicator_rsi_14"],
        start="2024-01-01",
        end="2024-01-31",
    )
    result = feature_service.get_indicators(query)

    # Verify: Result includes metadata columns
    assert not result.is_empty()
    assert "indicator_id" in result.columns
    assert "value" in result.columns
    # Metadata should be joined
    assert "name" in result.columns or "code" in result.columns


def test_get_indicators_filters_by_type(feature_service: FeatureService) -> None:
    """Test filtering by indicator type."""
    # Register indicators
    feature_service._metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        indicator_type="momentum",
        description="RSI",
        formula="RSI",
        parameters="{}",
    )
    feature_service._metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        indicator_type="trend",
        description="MA",
        formula="MA",
        parameters="{}",
    )

    # Write mixed data
    df = pl.DataFrame(
        {
            "sid": [1, 1],
            "trade_date": ["2024-01-02", "2024-01-02"],
            "indicator_id": ["indicator_rsi_14", "indicator_ma_20"],
            "indicator_type": ["momentum", "trend"],
            "value": [65.5, 10.2],
            "calc_time": ["2024-01-02 15:00:00"] * 2,
        }
    )
    feature_service._indicator_store.write(df, year=2024)

    # Query only momentum
    query = FeatureQuery(
        indicator_types=["momentum"],
        start="2024-01-01",
        end="2024-01-31",
    )
    result = feature_service.get_indicators(query)

    assert len(result) == 1
    assert result["indicator_id"][0] == "indicator_rsi_14"
