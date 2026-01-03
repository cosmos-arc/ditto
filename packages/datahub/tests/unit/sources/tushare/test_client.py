"""Tests for TushareClient."""

import os

import pytest
import pytest_mock
from ditto_datahub.sources.base import SourceConfigurationError
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
