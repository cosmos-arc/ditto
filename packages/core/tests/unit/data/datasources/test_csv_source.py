"""Unit tests for CSV data source."""

import tempfile
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_core.data.datasources.csv_source import CSVDataSource
from ditto_core.data.exceptions import ValidationError


class TestCSVDataSource:
    """Test CSV data source implementation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.config = {
            "data_dir": str(self.test_dir),
            "etf_list_file": "etf_list.csv",
        }

    def test_init_with_default_config(self) -> None:
        """Test CSV source initialization with default config."""
        source = CSVDataSource()
        assert source.source_type == "csv"
        assert source.data_dir == Path("data/test")
        assert source.etf_list_file == "etf_list.csv"

    def test_init_with_custom_config(self) -> None:
        """Test CSV source initialization with custom config."""
        source = CSVDataSource(self.config)
        assert source.source_type == "csv"
        assert source.data_dir == self.test_dir
        assert source.etf_list_file == "etf_list.csv"

    def test_connect_creates_directories(self) -> None:
        """Test that connect creates necessary directories."""
        source = CSVDataSource(self.config)

        # Remove directory to test creation
        if self.test_dir.exists():
            self.test_dir.rmdir()

        source.connect()

        assert self.test_dir.exists()
        assert (self.test_dir / "daily").exists()

    def test_connect_no_action_when_exists(self) -> None:
        """Test that connect works when directories already exist."""
        source = CSVDataSource(self.config)

        # Create directories manually
        (self.test_dir / "daily").mkdir(parents=True)

        # Should not raise error
        source.connect()

    def test_disconnect_no_action(self) -> None:
        """Test that disconnect does nothing (CSV has no connections)."""
        source = CSVDataSource(self.config)

        # Should not raise error
        source.disconnect()

    def test_get_etf_list_file_not_exists(self) -> None:
        """Test get_etf_list when file doesn't exist."""
        source = CSVDataSource(self.config)
        source.connect()

        result = source.get_etf_list()

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
        assert list(result.columns) == ["symbol", "name", "market", "list_date"]

    def test_get_etf_list_with_valid_file(self) -> None:
        """Test get_etf_list with valid CSV file."""
        # Create test ETF list file
        etf_data = """symbol,name,market,list_date
510300.SH,CSI300ETF,SSE,2012-05-04
516010.SH,CSI300ETFEFund,SSE,2019-10-14
513100.SH,NASDAQETF,SSE,2013-04-25
000300.SH,CSI300Index,SZSE,2005-04-08
"""
        etf_file = self.test_dir / "etf_list.csv"
        etf_file.write_text(etf_data, encoding="utf-8")

        source = CSVDataSource(self.config)
        source.connect()

        result = source.get_etf_list()

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 4
        assert list(result.columns) == ["symbol", "name", "market", "list_date"]
        assert result["symbol"].to_list() == [
            "510300.SH",
            "516010.SH",
            "513100.SH",
            "000300.SH",
        ]

    def test_get_etf_list_with_invalid_file(self) -> None:
        """Test get_etf_list with invalid CSV file."""
        # Create invalid ETF list file
        etf_data = """invalid,data
wrong,format
"""
        etf_file = self.test_dir / "etf_list.csv"
        etf_file.write_text(etf_data, encoding="utf-8")

        source = CSVDataSource(self.config)
        source.connect()

        with pytest.raises(ValidationError) as exc_info:
            source.get_etf_list()

        assert "CSV missing required columns" in str(exc_info.value)
        assert exc_info.value.source == "csv"

    def test_get_daily_data_file_not_exists(self) -> None:
        """Test get_daily_data when file doesn't exist."""
        source = CSVDataSource(self.config)
        source.connect()

        result = source.get_daily_data("510300.SH", "2024-01-01", "2024-01-31")

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
        assert list(result.columns) == [
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        ]

    def test_get_daily_data_with_valid_file(self) -> None:
        """Test get_daily_data with valid CSV file."""
        # Create test daily data file
        daily_data = """symbol,date,open,high,low,close,volume,amount
510300.SH,2024-01-02,3.500,3.550,3.480,3.520,1000000,3520000.00
510300.SH,2024-01-03,3.520,3.580,3.510,3.570,1200000,4256000.00
510300.SH,2024-01-04,3.570,3.600,3.530,3.550,1100000,3890000.00
516010.SH,2024-01-02,1.800,1.850,1.790,1.840,500000,920000.00
516010.SH,2024-01-03,1.840,1.890,1.830,1.880,600000,1128000.00
"""
        daily_dir = self.test_dir / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / "510300.SH.csv"
        daily_file.write_text(daily_data, encoding="utf-8")

        source = CSVDataSource(self.config)
        source.connect()

        result = source.get_daily_data("510300.SH", "2024-01-01", "2024-01-31")

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        assert list(result.columns) == [
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        ]
        assert all(result["symbol"] == "510300.SH")
        dates = result["date"].to_list()
        expected_dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
        assert len(dates) == len(expected_dates)
        for actual, expected in zip(dates, expected_dates, strict=False):
            assert actual == expected

    def test_get_daily_data_date_filtering(self) -> None:
        """Test get_daily_data with date range filtering."""
        # Create test daily data file
        daily_data = """symbol,date,open,high,low,close,volume,amount
510300.SH,2023-12-28,3.450,3.480,3.430,3.470,900000,3123000.00
510300.SH,2024-01-02,3.500,3.550,3.480,3.520,1000000,3520000.00
510300.SH,2024-01-03,3.520,3.580,3.510,3.570,1200000,4256000.00
510300.SH,2024-01-04,3.570,3.600,3.530,3.550,1100000,3890000.00
510300.SH,2024-02-01,3.550,3.620,3.540,3.610,1300000,4693000.00
"""
        daily_dir = self.test_dir / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / "510300.SH.csv"
        daily_file.write_text(daily_data, encoding="utf-8")

        source = CSVDataSource(self.config)
        source.connect()

        # Test date range filtering
        result = source.get_daily_data("510300.SH", "2024-01-01", "2024-01-31")

        assert len(result) == 3
        dates = result["date"].to_list()
        assert dates[0] >= date(2024, 1, 1)
        assert dates[2] <= date(2024, 1, 31)

    def test_get_daily_data_with_invalid_file(self) -> None:
        """Test get_daily_data with invalid CSV file."""
        # Create invalid daily data file
        daily_data = """invalid,data
wrong,format
"""
        daily_dir = self.test_dir / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / "510300.SH.csv"
        daily_file.write_text(daily_data, encoding="utf-8")

        source = CSVDataSource(self.config)
        source.connect()

        with pytest.raises(ValidationError) as exc_info:
            source.get_daily_data("510300.SH", "2024-01-01", "2024-01-31")

        assert "CSV missing required columns" in str(exc_info.value)
        assert exc_info.value.source == "csv"

    def test_get_etf_list_empty_file(self) -> None:
        """Test get_etf_list with empty file."""
        etf_file = self.test_dir / "etf_list.csv"
        etf_file.write_text("", encoding="utf-8")

        source = CSVDataSource(self.config)
        source.connect()

        result = source.get_etf_list()

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0

    def test_get_daily_data_empty_file(self) -> None:
        """Test get_daily_data with empty file."""
        daily_dir = self.test_dir / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / "510300.SH.csv"
        daily_file.write_text("", encoding="utf-8")

        source = CSVDataSource(self.config)
        source.connect()

        result = source.get_daily_data("510300.SH", "2024-01-01", "2024-01-31")

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
