"""
FeatureService unit tests.

技术指标服务单元测试.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.feature_service import FeatureQuery, FeatureService


class TestFeatureService:
    """FeatureService test suite."""

    def test_find_indicators_with_valid_query(
        self,
        tmp_path: Path,
        mock_indicator_reader: MagicMock,
        mock_indicator_writer: MagicMock,
        mock_metadata_reader: MagicMock,
        mock_metadata_writer: MagicMock,
    ) -> None:
        """Test find_indicators with valid query returns expected DataFrame."""
        # Arrange
        service = FeatureService(
            indicator_reader=mock_indicator_reader,
            indicator_writer=mock_indicator_writer,
            metadata_reader=mock_metadata_reader,
            metadata_writer=mock_metadata_writer,
        )

        # Mock indicator data
        mock_indicator_df = pl.DataFrame(
            {
                "indicator_id": ["1", "2"],
                "trade_date": ["2024-01-02", "2024-01-02"],
                "code": ["000001.SZ", "000001.SZ"],
                "value": [100.0, 200.0],
            }
        )
        mock_indicator_reader.read.return_value = mock_indicator_df

        # Mock metadata
        mock_metadata_df = pl.DataFrame(
            {
                "code": ["1", "2"],
                "name": ["SMA", "EMA"],
                "type": ["trend", "trend"],
                "description": ["Simple MA", "Exponential MA"],
            }
        )
        mock_metadata_reader.batch_get_by_codes.return_value = mock_metadata_df

        query = FeatureQuery(
            indicators=["1", "2"],
            start="2024-01-01",
            end="2024-01-31",
            indicator_types=["trend"],
        )

        # Act
        result = service.find_indicators(query)

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        assert "name" in result.columns
        assert "type" in result.columns
        assert "description" in result.columns

    def test_find_indicators_with_empty_result(
        self,
        tmp_path: Path,
        mock_indicator_reader: MagicMock,
        mock_indicator_writer: MagicMock,
        mock_metadata_reader: MagicMock,
        mock_metadata_writer: MagicMock,
    ) -> None:
        """Test find_indicators with no data returns empty DataFrame."""
        # Arrange
        service = FeatureService(
            indicator_reader=mock_indicator_reader,
            indicator_writer=mock_indicator_writer,
            metadata_reader=mock_metadata_reader,
            metadata_writer=mock_metadata_writer,
        )

        mock_indicator_reader.read.return_value = pl.DataFrame()

        query = FeatureQuery(
            indicators=["999"],
            start="2024-01-01",
            end="2024-01-31",
        )

        # Act
        result = service.find_indicators(query)

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()

    def test_list_indicators_convenience(
        self,
        tmp_path: Path,
        mock_indicator_reader: MagicMock,
        mock_indicator_writer: MagicMock,
        mock_metadata_reader: MagicMock,
        mock_metadata_writer: MagicMock,
    ) -> None:
        """Test list_indicators convenience method."""
        # Arrange
        service = FeatureService(
            indicator_reader=mock_indicator_reader,
            indicator_writer=mock_indicator_writer,
            metadata_reader=mock_metadata_reader,
            metadata_writer=mock_metadata_writer,
        )

        mock_indicator_df = pl.DataFrame(
            {
                "indicator_id": ["1"],
                "trade_date": ["2024-01-02"],
                "code": ["000001.SZ"],
                "value": [100.0],
            }
        )
        mock_indicator_reader.read.return_value = mock_indicator_df

        mock_metadata_df = pl.DataFrame(
            {
                "code": ["1"],
                "name": ["SMA"],
                "type": ["trend"],
                "description": ["Simple MA"],
            }
        )
        mock_metadata_reader.batch_get_by_codes.return_value = mock_metadata_df

        # Act
        result = service.list_indicators(
            "2024-01-01", "2024-01-31", indicator_types=["trend"]
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 1

    def test_list_indicators_without_type_filter(
        self,
        tmp_path: Path,
        mock_indicator_reader: MagicMock,
        mock_indicator_writer: MagicMock,
        mock_metadata_reader: MagicMock,
        mock_metadata_writer: MagicMock,
    ) -> None:
        """Test list_indicators without indicator_types filter."""
        # Arrange
        service = FeatureService(
            indicator_reader=mock_indicator_reader,
            indicator_writer=mock_indicator_writer,
            metadata_reader=mock_metadata_reader,
            metadata_writer=mock_metadata_writer,
        )

        mock_indicator_df = pl.DataFrame(
            {
                "indicator_id": ["1"],
                "trade_date": ["2024-01-02"],
                "code": ["000001.SZ"],
                "value": [100.0],
            }
        )
        mock_indicator_reader.read.return_value = mock_indicator_df

        mock_metadata_df = pl.DataFrame(
            {
                "code": ["1"],
                "name": ["SMA"],
                "type": ["trend"],
                "description": ["Simple MA"],
            }
        )
        mock_metadata_reader.batch_get_by_codes.return_value = mock_metadata_df

        # Act
        result = service.list_indicators("2024-01-01", "2024-01-31")

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 1


@pytest.fixture
def mock_indicator_reader(tmp_path: Path) -> MagicMock:
    """Create mock TechnicalIndicatorReader."""
    return MagicMock()


@pytest.fixture
def mock_indicator_writer(tmp_path: Path) -> MagicMock:
    """Create mock TechnicalIndicatorWriter."""
    return MagicMock()


@pytest.fixture
def mock_metadata_reader() -> MagicMock:
    """Create mock TechnicalIndicatorMetadataReader."""
    return MagicMock()


@pytest.fixture
def mock_metadata_writer() -> MagicMock:
    """Create mock TechnicalIndicatorMetadataWriter."""
    return MagicMock()
