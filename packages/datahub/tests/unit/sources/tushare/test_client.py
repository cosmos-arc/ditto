"""Tests for TushareClient."""

import os
from unittest import mock

import pytest
from ditto_datahub.sources.base import SourceConfigurationError
from ditto_datahub.sources.tushare.client import TushareClient


class TestTushareClientInit:
    """Tests for TushareClient initialization."""

    def test_init_with_token_from_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
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

        with mock.patch(
            "ditto_datahub.sources.tushare.client._get_tushare_token",
            side_effect=mock_get_token,
        ):
            client = TushareClient()
            assert client._token == "test_token_123"

    def test_init_missing_token_raises_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test missing token raises configuration error."""

        # Mock _get_tushare_token to always raise error
        def mock_get_token(token: str | None = None) -> str:
            raise SourceConfigurationError("Token not found")

        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

        with mock.patch(
            "ditto_datahub.sources.tushare.client._get_tushare_token",
            side_effect=mock_get_token,
        ):
            with pytest.raises(SourceConfigurationError):
                TushareClient()

    def test_init_custom_rate_limit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test custom rate limit configuration."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        client = TushareClient(rate_limit=100, window_seconds=60)
        assert client._rate_limit == 100
        assert client._window_seconds == 60

    def test_init_custom_retry_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test custom retry configuration."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        client = TushareClient(max_retries=3, retry_backoff=2.0)
        assert client._max_retries == 3
        assert client._retry_backoff == 2.0
