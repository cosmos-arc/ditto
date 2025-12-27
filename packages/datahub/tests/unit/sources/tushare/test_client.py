"""Tests for TushareClient."""

import pytest
from ditto_datahub.sources.base import SourceConfigurationError
from ditto_datahub.sources.tushare.client import TushareClient


class TestTushareClientInit:
    """Tests for TushareClient initialization."""

    def test_init_with_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization reads token from environment."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

        client = TushareClient()
        assert client._token == "test_token_123"

    def test_init_missing_token_raises_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test missing token raises configuration error."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

        with pytest.raises(SourceConfigurationError) as exc_info:
            TushareClient()

        assert exc_info.value.details["env_var"] == "TUSHARE_TOKEN"

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
