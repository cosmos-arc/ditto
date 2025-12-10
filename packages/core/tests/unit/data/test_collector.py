"""Unit tests for DataCollector."""

from datetime import date
from unittest.mock import MagicMock

import pytest
from ditto_core.data.collector import DataCollector


class TestDataCollector:
    """Test DataCollector functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_factory = MagicMock()
        self.mock_service = MagicMock()
        self.collector = DataCollector(
            data_factory=self.mock_factory,
            data_service=self.mock_service,
            batch_size=500,
            max_concurrent_fetches=2,
        )

    def test_initialization(self) -> None:
        """Test DataCollector initialization."""
        assert self.collector.data_factory == self.mock_factory
        assert self.collector.data_service == self.mock_service
        assert self.collector.batch_size == 500
        assert self.collector.max_concurrent_fetches == 2

    def test_initialization_with_defaults(self) -> None:
        """Test DataCollector initialization with default values."""
        collector = DataCollector(
            data_factory=self.mock_factory, data_service=self.mock_service
        )
        assert collector.batch_size == 1000
        assert collector.max_concurrent_fetches == 3

    @pytest.mark.asyncio
    async def test_update_etf_list(self) -> None:
        """Test updating ETF list."""
        result = await self.collector.update_etf_list()

        assert isinstance(result, dict)
        assert result["updated"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_update_etf_list_force_update(self) -> None:
        """Test updating ETF list with force_update."""
        result = await self.collector.update_etf_list(force_update=True)

        assert isinstance(result, dict)
        assert result["updated"] == 0

    @pytest.mark.asyncio
    async def test_update_daily_data(self) -> None:
        """Test updating daily market data."""
        test_date = date(2024, 1, 1)
        result = await self.collector.update_daily_data(
            ts_codes=["000001.SZ", "000002.SZ"],
            start_date=test_date,
            end_date=test_date,
        )

        assert isinstance(result, dict)
        assert result["total_records"] == 0
        assert result["updated"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_update_daily_data_no_params(self) -> None:
        """Test updating daily data with no parameters."""
        result = await self.collector.update_daily_data()

        assert isinstance(result, dict)
        assert "total_records" in result
        assert "updated" in result
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_update_adj_factors(self) -> None:
        """Test updating adjustment factors."""
        result = await self.collector.update_adj_factors(
            ts_codes=["000001.SZ"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert isinstance(result, dict)
        assert result["total_records"] == 0
        assert result["updated"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_verify_data_quality(self) -> None:
        """Test verifying data quality for a symbol."""
        result = await self.collector.verify_data_quality(
            symbol="000001.SZ", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
        )

        assert isinstance(result, dict)
        assert result["symbol"] == "000001.SZ"
        assert result["issues"] == []
        assert result["quality_score"] == 100.0

    @pytest.mark.asyncio
    async def test_verify_data_quality_no_dates(self) -> None:
        """Test verifying data quality without date range."""
        result = await self.collector.verify_data_quality(symbol="000001.SZ")

        assert result["symbol"] == "000001.SZ"
        assert isinstance(result["issues"], list)
        assert isinstance(result["quality_score"], float)

    @pytest.mark.asyncio
    async def test_validate_daily_data(self) -> None:
        """Test validating daily data for a symbol."""
        mock_data = MagicMock()
        result = await self.collector._validate_daily_data("000001.SZ", mock_data)

        assert isinstance(result, list)
        assert result == []
