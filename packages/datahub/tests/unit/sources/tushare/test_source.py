"""Tests for TushareSource."""

from datetime import date
from unittest import mock

import pandas as pd
import polars as pl
import pytest
from ditto_datahub.sources.base import SourceFetchError
from ditto_datahub.sources.metadata import (
    IncrementalMode,
)
from ditto_datahub.sources.tushare.source import TushareSource


class TestTushareSourceCalendar:
    """Tests for TushareSource.fetch_calendar."""

    def test_fetch_calendar_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_calendar returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response (pandas DataFrame like actual API)
        mock_response = pd.DataFrame(
            {
                "cal_date": ["20240101", "20240102", "20240103"],
                "is_open": [0, 1, 1],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_calendar("2024-01-01", "2024-01-03")

        # Verify schema
        assert result.schema == {
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {"trade_date": date(2024, 1, 1), "is_open": False},
            {"trade_date": date(2024, 1, 2), "is_open": True},
            {"trade_date": date(2024, 1, 3), "is_open": True},
        ]

    def test_fetch_calendar_empty_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_calendar handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame({"cal_date": [], "is_open": []})

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_calendar("2024-01-01", "2024-01-03")

        assert result.is_empty()

    def test_fetch_calendar_api_error_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_calendar raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.side_effect = Exception("API error")

            source = TushareSource()

            with pytest.raises(SourceFetchError):
                source.fetch_calendar("2024-01-01", "2024-01-03")


class TestTushareSourceEtfBasic:
    """Tests for TushareSource.fetch_etf_basic."""

    def test_fetch_etf_basic_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_etf_basic returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response (pandas DataFrame like actual API)
        # Note: API returns csname, not etf_name; exchange is already SSE/SZSE
        mock_response = pd.DataFrame(
            {
                "ts_code": ["510300.SH", "159919.SZ"],
                "csname": ["沪深300ETF", "沪深300ETF"],
                "exchange": ["SSE", "SZSE"],
                "list_date": ["20120706", "20190624"],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_etf_basic()

        # Verify schema
        assert result.schema == {
            "src_code": pl.String,
            "symbol": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify data transformation (exchange already in correct format)
        assert result.to_dicts() == [
            {
                "src_code": "510300.SH",
                "symbol": "510300",
                "name": "沪深300ETF",
                "exchange": "SSE",
                "list_date": date(2012, 7, 6),
            },
            {
                "src_code": "159919.SZ",
                "symbol": "159919",
                "name": "沪深300ETF",
                "exchange": "SZSE",
                "list_date": date(2019, 6, 24),
            },
        ]

    def test_fetch_etf_basic_empty_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_etf_basic handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": [],
                "csname": [],
                "exchange": [],
                "list_date": [],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_etf_basic()

        assert result.is_empty()


class TestTushareSourceEtfDaily:
    """Tests for TushareSource.fetch_etf_daily."""

    def test_fetch_etf_daily_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_etf_daily returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response (pandas DataFrame like actual API)
        # Note: fund_daily API returns vol, amount, pct_chg
        mock_response = pd.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "trade_date": ["20240102"],
                "pre_close": [3.5],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "change": [0.05],
                "pct_chg": [1.5],
                "vol": [100000.0],
                "amount": [355000.0],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_etf_daily("2024-01-02")

        # Verify schema matches ETF_DAILY_SCHEMA
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation (vol->volume, pct_chg->pct_change)
        assert result.to_dicts() == [
            {
                "src_code": "510300.SH",
                "trade_date": date(2024, 1, 2),
                "open": 3.5,
                "high": 3.6,
                "low": 3.4,
                "close": 3.55,
                "pre_close": 3.5,
                "volume": 100000.0,
                "amount": 355000.0,
                "pct_change": 1.5,
            },
        ]

    def test_fetch_etf_daily_empty_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_etf_daily handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": [],
                "trade_date": [],
                "pre_close": [],
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "change": [],
                "pct_chg": [],
                "vol": [],
                "amount": [],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_etf_daily("2024-01-02")

        assert result.is_empty()


class TestTushareSourceStockBasic:
    """Tests for TushareSource.fetch_stock_basic."""

    def test_fetch_stock_basic_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_stock_basic returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response (pandas DataFrame like actual API)
        # Note: stock_basic API returns ts_code, symbol, name, exchange, list_date
        mock_response = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "symbol": ["000001", "600000"],
                "name": ["平安银行", "浦发银行"],
                "exchange": ["SZSE", "SSE"],
                "list_date": ["19910403", "19991110"],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_stock_basic()

        # Verify schema
        assert result.schema == {
            "src_code": pl.String,
            "symbol": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify data transformation
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "exchange": "SZSE",
                "list_date": date(1991, 4, 3),
            },
            {
                "src_code": "600000.SH",
                "symbol": "600000",
                "name": "浦发银行",
                "exchange": "SSE",
                "list_date": date(1999, 11, 10),
            },
        ]

    def test_fetch_stock_basic_empty_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_stock_basic handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": [],
                "symbol": [],
                "name": [],
                "exchange": [],
                "list_date": [],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_stock_basic()

        assert result.is_empty()

    def test_fetch_stock_basic_api_error_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_stock_basic raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.side_effect = Exception("API error")

            source = TushareSource()

            with pytest.raises(SourceFetchError):
                source.fetch_stock_basic()


class TestTushareSourceStockDaily:
    """Tests for TushareSource.fetch_stock_daily."""

    def test_fetch_stock_daily_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_stock_daily returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response (pandas DataFrame like actual API)
        # Note: daily API returns vol, amount, pct_chg (same as fund_daily)
        mock_response = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240102"],
                "pre_close": [11.5],
                "open": [11.5],
                "high": [11.8],
                "low": [11.3],
                "close": [11.6],
                "change": [0.1],
                "pct_chg": [0.87],
                "vol": [12500000.0],
                "amount": [145000000.0],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_stock_daily("2024-01-02")

        # Verify schema matches STOCK_DAILY_SCHEMA (same as ETF daily)
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation (vol->volume, pct_chg->pct_change)
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "open": 11.5,
                "high": 11.8,
                "low": 11.3,
                "close": 11.6,
                "pre_close": 11.5,
                "volume": 12500000.0,
                "amount": 145000000.0,
                "pct_change": 0.87,
            },
        ]

    def test_fetch_stock_daily_empty_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_stock_daily handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": [],
                "trade_date": [],
                "pre_close": [],
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "change": [],
                "pct_chg": [],
                "vol": [],
                "amount": [],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_stock_daily("2024-01-02")

        assert result.is_empty()

    def test_fetch_stock_daily_api_error_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_stock_daily raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.side_effect = Exception("API error")

            source = TushareSource()

            with pytest.raises(SourceFetchError):
                source.fetch_stock_daily("2024-01-02")


class TestTushareSourceAdjFactor:
    """Tests for TushareSource.fetch_adj_factor."""

    def test_fetch_adj_factor_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_adj_factor returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response (pandas DataFrame like actual API)
        # Note: adj_factor API returns ts_code, trade_date, adj_factor
        mock_response = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "trade_date": ["20240102", "20240102"],
                "adj_factor": [1.2345, 1.5678],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_adj_factor("2024-01-02")

        # Verify schema
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.2345,
            },
            {
                "src_code": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.5678,
            },
        ]

    def test_fetch_adj_factor_empty_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_adj_factor handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": [],
                "trade_date": [],
                "adj_factor": [],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_adj_factor("2024-01-02")

        assert result.is_empty()

    def test_fetch_adj_factor_api_error_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_adj_factor raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.side_effect = Exception("API error")

            source = TushareSource()

            with pytest.raises(SourceFetchError):
                source.fetch_adj_factor("2024-01-02")


class TestTushareSourceFundAdj:
    """Tests for TushareSource.fetch_fund_adj."""

    def test_fetch_fund_adj_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_fund_adj returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response (pandas DataFrame like actual API)
        # Note: fund_adj API returns ts_code, trade_date, adj_factor
        # (same as adj_factor)
        mock_response = pd.DataFrame(
            {
                "ts_code": ["510300.SH", "159919.SZ"],
                "trade_date": ["20240102", "20240102"],
                "adj_factor": [1.0123, 1.0456],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_fund_adj("2024-01-02")

        # Verify schema
        expected_schema = {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }
        assert result.schema == expected_schema

        # Verify data transformation
        assert result.to_dicts() == [
            {
                "src_code": "510300.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.0123,
            },
            {
                "src_code": "159919.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 2),
                "adj_factor": 1.0456,
            },
        ]

    def test_fetch_fund_adj_empty_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_fund_adj handles empty response."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": [],
                "trade_date": [],
                "adj_factor": [],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_fund_adj("2024-01-02")

        assert result.is_empty()

    def test_fetch_fund_adj_api_error_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_fund_adj raises SourceFetchError on API error."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.side_effect = Exception("API error")

            source = TushareSource()

            with pytest.raises(SourceFetchError):
                source.fetch_fund_adj("2024-01-02")


class TestTushareSourceIncremental:
    """Tests for TushareSource.fetch_etf_daily_incremental."""

    def test_quick_mode_skips_when_uptodate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test QUICK mode skips fetch when trade_date <= last_trade_date."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        source = TushareSource()

        # Call with last_trade_date equal to trade_date - should skip
        df, metadata = source.fetch_etf_daily_incremental(
            trade_date="2024-12-27",
            mode=IncrementalMode.QUICK,
            last_trade_date="2024-12-27",
        )

        # Should return empty DataFrame and metadata with no new data
        assert df.is_empty()
        assert metadata.last_trade_date == "2024-12-27"
        assert metadata.last_rows == 0

    def test_quick_mode_fetches_when_stale(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test QUICK mode fetches when trade_date > last_trade_date."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "trade_date": ["20241227"],
                "pre_close": [3.5],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "change": [0.05],
                "pct_chg": [1.5],
                "vol": [100000.0],
                "amount": [355000.0],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            _, metadata = source.fetch_etf_daily_incremental(
                trade_date="2024-12-27",
                mode=IncrementalMode.QUICK,
                last_trade_date="2024-12-26",
            )

        # Should return data and updated metadata
        assert metadata.last_trade_date == "2024-12-27"
        assert metadata.last_rows == 1
        assert metadata.last_checksum is not None

    def test_precise_mode_fetches_when_checksum_differs(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test PRECISE mode fetches when checksum differs."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "trade_date": ["20241227"],
                "pre_close": [3.5],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "change": [0.05],
                "pct_chg": [1.5],
                "vol": [100000.0],
                "amount": [355000.0],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            df, metadata = source.fetch_etf_daily_incremental(
                trade_date="2024-12-27",
                mode=IncrementalMode.PRECISE,
                last_trade_date="2024-12-27",
                last_checksum="different_checksum",
            )

        # Should fetch because checksum differs
        assert not df.is_empty()
        assert metadata.last_checksum != "different_checksum"

    def test_precise_mode_skips_when_checksum_matches(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test PRECISE mode skips when checksum matches."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "trade_date": ["20241227"],
                "pre_close": [3.5],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "change": [0.05],
                "pct_chg": [1.5],
                "vol": [100000.0],
                "amount": [355000.0],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()

            # First, fetch to get the checksum
            _, metadata1 = source.fetch_etf_daily_incremental(
                trade_date="2024-12-27",
                mode=IncrementalMode.PRECISE,
                last_trade_date="2024-12-26",
            )
            expected_checksum = metadata1.last_checksum

            # Second, call with same checksum - should skip
            df2, metadata2 = source.fetch_etf_daily_incremental(
                trade_date="2024-12-27",
                mode=IncrementalMode.PRECISE,
                last_trade_date="2024-12-27",
                last_checksum=expected_checksum,
            )

        # Should skip because checksum matches
        assert df2.is_empty()
        assert metadata2.last_rows == 0

    def test_incremental_returns_metadata_with_dataset_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test incremental fetch returns correct metadata."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        mock_response = pd.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "trade_date": ["20241227"],
                "pre_close": [3.5],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "change": [0.05],
                "pct_chg": [1.5],
                "vol": [100000.0],
                "amount": [355000.0],
            }
        )

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            _, metadata = source.fetch_etf_daily_incremental(
                trade_date="2024-12-27",
                mode=IncrementalMode.QUICK,
                last_trade_date="2024-12-26",
            )

        assert metadata.dataset == "etf_daily"
        assert metadata.source == "tushare"
