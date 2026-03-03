"""Tests for FredClient."""

from __future__ import annotations

import httpx
import pytest
from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
)
from ditto_datahub.sources.fred.client import FredClient


class TestFredClientInit:
    """Tests for FredClient initialization."""

    def test_init_with_api_key_parameter(self) -> None:
        """Test initialization with explicit API key."""
        client = FredClient(api_key="test_api_key_123")
        assert client._api_key == "test_api_key_123"

    def test_init_missing_api_key_raises_error(self, monkeypatch) -> None:
        """Test missing API key raises configuration error."""
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        with pytest.raises(SourceConfigurationError) as exc_info:
            FredClient()
        assert "FRED_API_KEY" in str(exc_info.value)

    def test_init_with_env_var(self, monkeypatch) -> None:
        """Test initialization reads API key from environment variable."""
        monkeypatch.setenv("FRED_API_KEY", "env_api_key_456")
        client = FredClient()
        assert client._api_key == "env_api_key_456"

    def test_init_parameter_overrides_env_var(self, monkeypatch) -> None:
        """Test explicit API key parameter overrides environment variable."""
        monkeypatch.setenv("FRED_API_KEY", "env_api_key")
        client = FredClient(api_key="explicit_key")
        assert client._api_key == "explicit_key"


class TestFredClientGetSeriesObservations:
    """Tests for FredClient.get_series_observations method."""

    def test_successful_fetch_returns_dataframe(self, respx_mock) -> None:
        """成功获取返回 polars DataFrame."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                        {
                            "realtime_start": "2024-03-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-02-01",
                            "value": "3.9",
                        },
                    ],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert
        assert result.height == 2
        assert "date" in result.columns
        assert "value" in result.columns
        assert "realtime_start" in result.columns

    def test_empty_response_returns_empty_dataframe(self, respx_mock) -> None:
        """空响应返回空 DataFrame，带正确 schema."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert
        assert result.height == 0
        assert "date" in result.columns
        assert "value" in result.columns

    def test_auth_error_raises_authentication_error(self, respx_mock) -> None:
        """401 错误抛出 SourceAuthenticationError."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        # Act & Assert
        client = FredClient(api_key="invalid_key")
        with pytest.raises(SourceAuthenticationError):
            client.get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

    def test_network_error_raises_fetch_error(self, respx_mock) -> None:
        """网络错误最终抛出异常."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=httpx.NetworkError("Connection failed")
        )

        # Act & Assert
        client = FredClient(api_key="test_key")
        # Tenacity wraps the exception in RetryError after retries
        import tenacity

        with pytest.raises(tenacity.RetryError) as exc_info:
            client.get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

        # Verify the original exception is SourceFetchError
        assert isinstance(exc_info.value.__cause__, SourceFetchError)

    def test_pit_parameters_included_in_request(self, respx_mock) -> None:
        """PIT 参数 (realtime_start/end) 包含在请求中."""
        # Arrange
        request_capture = None

        def capture_request(request: httpx.Request) -> httpx.Response:
            nonlocal request_capture
            request_capture = request
            return httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "GDP",
                    "observations": [],
                },
            )

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=capture_request
        )

        # Act
        client = FredClient(api_key="test_key")
        client.get_series_observations(
            series_id="GDP",
            observation_start="2020-01-01",
            observation_end="2024-12-31",
            realtime_start="2024-01-01",
            realtime_end="2024-12-31",
        )

        # Assert
        assert request_capture is not None
        params = dict(request_capture.url.params)
        assert params.get("realtime_start") == "2024-01-01"
        assert params.get("realtime_end") == "2024-12-31"

    def test_value_column_parsed_as_float(self, respx_mock) -> None:
        """value 列解析为 Float64."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                    ],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert

        assert str(result["value"].dtype) == "Float64"

    def test_date_columns_parsed_as_date(self, respx_mock) -> None:
        """日期列解析为 Date 类型."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                    ],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert
        assert str(result["date"].dtype) == "Date"
        assert str(result["realtime_start"].dtype) == "Date"


class TestFredClientResourceManagement:
    """Tests for FredClient resource management."""

    def test_close_method(self) -> None:
        """Test close method properly closes HTTP client."""
        client = FredClient(api_key="test_key")

        # Verify _client exists and is not closed
        assert client._client is not None
        assert not client._client.is_closed

        # Call close
        client.close()

        # Verify _client is closed
        assert client._client.is_closed

    def test_context_manager(self) -> None:
        """Test FredClient supports context manager protocol."""
        with FredClient(api_key="test_key") as client:
            assert client is not None
            assert isinstance(client, FredClient)
            # Verify client is not closed inside the with block
            assert not client._client.is_closed

        # After with block, client should be closed
        assert client._client.is_closed
