"""Tests for TushareSource."""

from datetime import date
from unittest import mock

import polars as pl
import pytest
from ditto_datahub.sources.base import SourceFetchError
from ditto_datahub.sources.tushare.source import TushareSource


class TestTushareSourceCalendar:
    """Tests for TushareSource.fetch_calendar."""

    def test_fetch_calendar_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetch_calendar returns DataFrame with correct schema."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Mock Tushare API response
        mock_response = {
            "fields": "cal_date,is_open",
            "items": [
                ["20240101", "0"],
                ["20240102", "1"],
                ["20240103", "1"],
            ],
        }

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

        mock_response = {"fields": "cal_date,is_open", "items": []}

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

        mock_response = {
            "fields": "ts_code,etf_name,exchange,list_date",
            "items": [
                ["510300.SH", "沪深300ETF", "上交所", "20120706"],
                ["159919.SZ", "沪深300ETF", "深交所", "20190624"],
            ],
        }

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

        # Verify data transformation (exchange mapping)
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

        mock_response = {"fields": "ts_code,etf_name,exchange,list_date", "items": []}

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

        mock_response = {
            "fields": (
                "ts_code,trade_date,open,high,low,close,pre_close,vol,amt,pct_chg"
            ),
            "items": [
                [
                    "510300.SH",
                    "20240102",
                    3.5,
                    3.6,
                    3.4,
                    3.55,
                    3.5,
                    100000,
                    355000,
                    1.5,
                ],
            ],
        }

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

        # Verify data transformation
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

        mock_response = {
            "fields": (
                "ts_code,trade_date,open,high,low,close,pre_close,vol,amt,pct_chg"
            ),
            "items": [],
        }

        with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:
            mock_api.return_value.query.return_value = mock_response

            source = TushareSource()
            result = source.fetch_etf_daily("2024-01-02")

        assert result.is_empty()
