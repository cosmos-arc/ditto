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
