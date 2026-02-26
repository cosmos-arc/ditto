"""Tests for CommodityFredAdapter."""

from __future__ import annotations

import httpx
from ditto_datahub.sources.fred.adapters.commodity import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    CommodityFredAdapter,
)
from ditto_datahub.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA


class TestCommodityFredAdapter:
    """Tests for CommodityFredAdapter."""

    def test_fetch_wti(self, respx_mock) -> None:
        """Test fetching WTI crude oil data."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "DCOILWTICO",
                    "observations": [
                        {
                            "realtime_start": "2024-01-15",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-15",
                            "value": "72.50",
                        },
                    ],
                },
            )
        )

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["COMMOD_WTI"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # Assert
        assert result.height == 1
        assert "instrument_id" in result.columns
        assert "close" in result.columns
        expected_id = COMMODITY_CODE_TO_INSTRUMENT_ID["COMMOD_WTI"]
        assert result["instrument_id"][0] == expected_id
        assert result["close"][0] == 72.50

    def test_fetch_commodities_returns_correct_schema(self, respx_mock) -> None:
        """Returns DataFrame with COMMODITY_SOURCE_SCHEMA columns."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "DCOILWTICO",
                    "observations": [
                        {
                            "realtime_start": "2024-01-15",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-15",
                            "value": "72.50",
                        },
                    ],
                },
            )
        )

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["COMMOD_WTI"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert - check schema columns
        expected_columns = set(COMMODITY_SOURCE_SCHEMA.schema.keys())
        assert set(result.columns) == expected_columns

    def test_fetch_commodities_ohlc_from_single_value(self, respx_mock) -> None:
        """FRED only provides close price, OHLC should all be same value."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "DCOILWTICO",
                    "observations": [
                        {
                            "realtime_start": "2024-01-15",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-15",
                            "value": "72.50",
                        },
                    ],
                },
            )
        )

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["COMMOD_WTI"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # Assert - OHLC should all be same
        assert result["open"][0] == 72.50
        assert result["high"][0] == 72.50
        assert result["low"][0] == 72.50
        assert result["close"][0] == 72.50

    def test_fetch_multiple_commodities(self, respx_mock) -> None:
        """Fetch multiple commodities."""
        # Arrange
        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            series_id = dict(request.url.params).get("series_id", "UNKNOWN")
            return httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": series_id,
                    "observations": [
                        {
                            "realtime_start": "2024-01-15",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-15",
                            "value": "100.0",
                        },
                    ],
                },
            )

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=side_effect
        )

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["COMMOD_WTI", "COMMOD_BRENT"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert
        assert call_count == 2
        assert result.height == 2

    def test_fetch_commodities_unknown_code_skipped(self, respx_mock) -> None:
        """Unknown commodity codes are skipped."""
        # Arrange - no mock needed as it should skip

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["UNKNOWN_COMMODITY"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert - empty dataframe with correct schema
        assert result.height == 0
        assert set(result.columns) == set(COMMODITY_SOURCE_SCHEMA.schema.keys())

    def test_fetch_commodities_non_commodity_code_skipped(self, respx_mock) -> None:
        """Non-commodity codes (like macro indicators) are skipped."""
        # Arrange - no mock needed as it should skip

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["US_UNRATE"],  # This is an employment indicator, not commodity
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert - empty dataframe with correct schema
        assert result.height == 0
        assert set(result.columns) == set(COMMODITY_SOURCE_SCHEMA.schema.keys())

    def test_fetch_commodities_empty_response(self, respx_mock) -> None:
        """Empty response returns empty DataFrame."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "DCOILWTICO",
                    "observations": [],
                },
            )
        )

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["COMMOD_WTI"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert
        assert result.height == 0
        assert set(result.columns) == set(COMMODITY_SOURCE_SCHEMA.schema.keys())

    def test_context_manager(self, respx_mock) -> None:
        """Adapter can be used as context manager."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "DCOILWTICO",
                    "observations": [],
                },
            )
        )

        # Act & Assert
        with CommodityFredAdapter(api_key="test_key") as adapter:
            result = adapter.fetch_commodities(
                codes=["COMMOD_WTI"],
                start_date="2024-01-01",
                end_date="2024-12-31",
            )
            assert result.height == 0

    def test_commodity_instrument_id_mapping(self) -> None:
        """Commodity codes map to correct instrument IDs in 5M range."""
        # Assert - all commodity instrument IDs should be in 5M range
        for code, instrument_id in COMMODITY_CODE_TO_INSTRUMENT_ID.items():
            assert 5_000_000 <= instrument_id < 6_000_000, (
                f"{code} instrument_id {instrument_id} not in 5M range"
            )

    def test_fetch_commodities_includes_vix(self, respx_mock) -> None:
        """VIX indicators are also supported as they are market data."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "VIXCLS",
                    "observations": [
                        {
                            "realtime_start": "2024-01-15",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-15",
                            "value": "15.5",
                        },
                    ],
                },
            )
        )

        # Act
        adapter = CommodityFredAdapter(api_key="test_key")
        result = adapter.fetch_commodities(
            codes=["VIX_30D"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # Assert
        assert result.height == 1
        expected_id = COMMODITY_CODE_TO_INSTRUMENT_ID["VIX_30D"]
        assert result["instrument_id"][0] == expected_id
