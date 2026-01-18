"""Tests for SourcesProvider."""

import pytest
from ditto_datahub.sources.provider import SourcesProvider


class TestSourcesProvider:
    """Tests for SourcesProvider."""

    def test_tushare_property_returns_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test tushare property returns TushareProvider instance."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        provider = SourcesProvider()
        source = provider.tushare

        assert source is not None
        assert hasattr(source, "fetch_calendar")
        assert hasattr(source, "fetch_etf_basic")
        assert hasattr(source, "fetch_etf_daily")

    def test_tushare_property_is_cached(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test tushare property is cached."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        provider = SourcesProvider()
        source1 = provider.tushare
        source2 = provider.tushare

        # Should return the same instance
        assert source1 is source2

    def test_get_returns_tushare_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test get() method returns TushareProvider."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        provider = SourcesProvider()
        source = provider.get("tushare")

        assert source is not None
        assert hasattr(source, "fetch_calendar")

    def test_get_is_case_insensitive(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test get() normalizes case."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        provider = SourcesProvider()
        source1 = provider.get("TUSHARE")
        source2 = provider.get("tushare")

        # Both should return valid source instances
        assert source1 is not None
        assert source2 is not None
        # Both should have the same type
        assert isinstance(source1, type(source2))

    def test_get_invalid_name_raises_error(self) -> None:
        """Test get() raises error for invalid source name."""
        provider = SourcesProvider()

        with pytest.raises(ValueError, match="Unknown source"):
            provider.get("invalid_source")
