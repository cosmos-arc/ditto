"""Tests for SourcesAccessor."""

import pytest
from ditto_datahub.sources.accessor import SourcesAccessor


class TestSourcesAccessor:
    """Tests for SourcesAccessor."""

    def test_tushare_property_returns_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test tushare property returns TushareSource instance."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        accessor = SourcesAccessor()
        source = accessor.tushare

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

        accessor = SourcesAccessor()
        source1 = accessor.tushare
        source2 = accessor.tushare

        # Should return the same instance
        assert source1 is source2

    def test_get_returns_tushare_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test get() method returns TushareSource."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        accessor = SourcesAccessor()
        source = accessor.get("tushare")

        assert source is not None
        assert hasattr(source, "fetch_calendar")

    def test_get_is_case_insensitive(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test get() normalizes case."""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        accessor = SourcesAccessor()
        source1 = accessor.get("TUSHARE")
        source2 = accessor.get("tushare")

        # Both should return valid source instances
        assert source1 is not None
        assert source2 is not None
        # Both should have the same type
        assert isinstance(source1, type(source2))

    def test_get_invalid_name_raises_error(self) -> None:
        """Test get() raises error for invalid source name."""
        accessor = SourcesAccessor()

        with pytest.raises(ValueError, match="Unknown source"):
            accessor.get("invalid_source")
