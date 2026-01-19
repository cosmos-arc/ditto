"""Tests for TushareClient."""

import os

import httpx
import pytest
import pytest_mock
from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
)
from ditto_datahub.sources.tushare.client import TushareClient
from ditto_datahub.sources.tushare.rate_limiter import (
    TushareRateLimitConfig,
    TushareRateLimiter,
)


class TestTushareClientInit:
    """Tests for TushareClient initialization."""

    def test_init_with_token_from_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test initialization reads token from environment."""

        # Mock _get_tushare_token to only read from env var
        def mock_get_token(token: str | None = None) -> str:
            if token:
                return token
            if env_token := os.getenv("TUSHARE_TOKEN"):
                return env_token
            raise SourceConfigurationError("Token not found")

        monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

        mocker.patch(
            "ditto_datahub.sources.tushare.client._get_tushare_token",
            side_effect=mock_get_token,
        )
        client = TushareClient()
        assert client._token == "test_token_123"

    def test_init_missing_token_raises_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test missing token raises configuration error."""

        # Mock _get_tushare_token to always raise error
        def mock_get_token(token: str | None = None) -> str:
            raise SourceConfigurationError("Token not found")

        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

        mocker.patch(
            "ditto_datahub.sources.tushare.client._get_tushare_token",
            side_effect=mock_get_token,
        )
        with pytest.raises(SourceConfigurationError):
            TushareClient()

    def test_init_custom_rate_limit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test custom rate limit configuration."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # 使用新的 rate_config API
        config = TushareRateLimitConfig(
            global_rate=100,
            global_window=60,
        )
        client = TushareClient(rate_config=config)
        assert isinstance(client._limiter, TushareRateLimiter)

    def test_init_custom_retry_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test custom retry configuration uses paid tier."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # 使用付费账户配置
        client = TushareClient(rate_config=TushareRateLimitConfig.paid())
        assert isinstance(client._limiter, TushareRateLimiter)


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
        client = TushareClient(token="test_token")
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

        client = TushareClient(token="test_token")
        wait_spy = mocker.spy(client._limiter, "wait_if_needed")

        # Act
        client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        wait_spy.assert_called_once()

    def test_retry_on_network_error(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        client = TushareClient(token="test_token")
        result = client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        assert call_count == 2  # 第一次失败,第二次成功
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
        client = TushareClient(token="invalid_token")
        with pytest.raises(SourceAuthenticationError):
            client.query("trade_cal", "cal_date", exchange="SSE")

    def test_retry_on_5xx_status(self, respx_mock) -> None:
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
        client = TushareClient(token="test_token")
        result = client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        assert call_count == 2
        assert result.height == 1


class TestTushareClientResourceManagement:
    """Tests for TushareClient resource management."""

    def test_close_method(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test close method properly closes HTTP client."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
        client = TushareClient()

        # Verify _client exists and is not closed
        assert client._client is not None
        assert not client._client.is_closed

        # Call close
        client.close()

        # Verify _client is closed
        assert client._client.is_closed

    def test_context_manager(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test TushareClient supports context manager protocol."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        with TushareClient() as client:
            assert client is not None
            assert isinstance(client, TushareClient)
            # Verify client is not closed inside the with block
            assert not client._client.is_closed

        # After with block, client should be closed
        assert client._client.is_closed
