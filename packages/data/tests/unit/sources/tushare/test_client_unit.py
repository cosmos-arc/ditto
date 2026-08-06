"""Tests for TushareClient."""

import httpx
import pytest
import pytest_mock
from ditto_data.config import DataSourceSettings
from ditto_data.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
)
from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.utils.rate_limiter import (
    TushareRateLimitConfig,
    TushareRateLimiter,
)


def _settings(token: str | None = None) -> DataSourceSettings:
    if token is None:
        token = "not_a_secret"
    return DataSourceSettings(tushare_token=token)


class TestTushareClientInit:
    """Tests for TushareClient initialization."""

    def test_init_with_token_from_settings(self) -> None:
        """Test initialization reads token from settings."""
        settings = _settings("test_token_123")
        client = TushareClient(settings=settings)
        assert client._token == "test_token_123"

    def test_init_missing_token_raises_error(self) -> None:
        """Test missing token raises configuration error."""
        with pytest.raises(SourceConfigurationError):
            TushareClient(settings=_settings(""))

    def test_init_custom_rate_limit(self) -> None:
        """Test custom rate limit configuration."""
        config = TushareRateLimitConfig(
            global_rate=100,
            global_window=60,
        )
        client = TushareClient(rate_config=config, settings=_settings())
        assert isinstance(client._limiter, TushareRateLimiter)

    def test_init_custom_retry_config(self) -> None:
        """Test custom retry configuration uses paid tier."""
        client = TushareClient(
            rate_config=TushareRateLimitConfig.paid(),
            settings=_settings(),
        )
        assert isinstance(client._limiter, TushareRateLimiter)

    def test_init_uses_explicit_paid_profile_from_settings(self) -> None:
        """Production paid profile must reach the shared provider limiter."""
        settings = DataSourceSettings(
            tushare_token="not_a_secret",
            rate_limit_profile="paid",
        )

        client = TushareClient(settings=settings)

        assert client._limiter._config == TushareRateLimitConfig.paid()

    def test_init_keeps_free_profile_as_the_default(self) -> None:
        """Development defaults stay conservative unless explicitly overridden."""
        client = TushareClient(settings=_settings())

        assert client._limiter._config == TushareRateLimitConfig.free()


class TestTushareClientQuery:
    """Tests for TushareClient.query method."""

    def test_successful_query_returns_dataframe(self, respx_mock) -> None:
        """成功查询返回 polars DataFrame."""
        # Arrange
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["cal_date", "is_open"],
                        "items": [["20240101", 0], ["20240102", 1]],
                    },
                },
            )
        )

        # Act
        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date,is_open", exchange="SSE")

        # Assert
        assert result.height == 2
        assert result.columns == ["cal_date", "is_open"]
        assert result.to_dict(as_series=False) == {
            "cal_date": ["20240101", "20240102"],
            "is_open": [0, 1],
        }

    def test_rate_limit_before_request(
        self, respx_mock, mocker: pytest_mock.MockFixture
    ) -> None:
        """请求前调用限流器."""
        # Arrange
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["20240101"]]},
                },
            )
        )

        client = TushareClient(token="test_token", settings=_settings())
        wait_spy = mocker.spy(client._limiter, "wait_if_needed")

        # Act
        client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        wait_spy.assert_called_once()

    def test_retry_on_network_error(self, respx_mock, fake_time) -> None:
        """网络错误自动重试."""
        # Arrange
        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.NetworkError("Connection failed")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["20240101"]]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        # Act
        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        assert call_count == 2  # [REVIEW],第二次成功
        assert result.height == 1

    def test_no_retry_on_auth_error(self, respx_mock) -> None:
        """认证错误不重试,直接抛出."""
        # Arrange
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={"code": 2002, "msg": "没有权限"},
            )
        )

        # Act & Assert
        client = TushareClient(token="invalid_token", settings=_settings())
        with pytest.raises(SourceAuthenticationError):
            client.query("trade_cal", "cal_date", exchange="SSE")

    def test_retry_on_5xx_status(self, respx_mock, fake_time) -> None:
        """5xx 状态码自动重试."""
        # Arrange
        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["20240101"]]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        # Act
        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        assert call_count == 2
        assert result.height == 1


class TestTushareClientResourceManagement:
    """Tests for TushareClient resource management."""

    def test_close_method(self) -> None:
        """Test close method properly closes HTTP client."""
        client = TushareClient(settings=_settings())

        # Verify _client exists and is not closed
        assert client._client is not None
        assert not client._client.is_closed

        # Call close
        client.close()

        # Verify _client is closed
        assert client._client.is_closed

    def test_context_manager(self) -> None:
        """Test TushareClient supports context manager protocol."""
        with TushareClient(settings=_settings()) as client:
            assert client is not None
            assert isinstance(client, TushareClient)
            # Verify client is not closed inside the with block
            assert not client._client.is_closed

        # After with block, client should be closed
        assert client._client.is_closed
