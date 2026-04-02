"""Tests for DataSources."""

import pytest
from ditto_data.sources.source import DataSources
from pytest_mock import MockerFixture


class TestDataSources:
    """Tests for DataSources."""

    def test_tushare_property_returns_source(self, mocker: MockerFixture) -> None:
        """Test tushare property returns TushareSource instance."""
        mock_tushare = mocker.Mock()
        mock_tushare.fetch_calendar = mocker.Mock()
        mock_tushare.fetch_etf_basic = mocker.Mock()
        mock_tushare.fetch_etf_daily = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        source = sources.tushare

        assert source is not None
        assert source is mock_tushare
        assert hasattr(source, "fetch_calendar")
        assert hasattr(source, "fetch_etf_basic")
        assert hasattr(source, "fetch_etf_daily")

    def test_tushare_property_is_cached(self, mocker: MockerFixture) -> None:
        """Test tushare property is cached."""
        mock_tushare = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        source1 = sources.tushare
        source2 = sources.tushare

        # Should return the same instance
        assert source1 is source2
        assert source1 is mock_tushare

    def test_get_returns_tushare_source(self, mocker: MockerFixture) -> None:
        """Test get() method returns TushareSource."""
        mock_tushare = mocker.Mock()
        mock_tushare.fetch_calendar = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        source = sources.get("tushare")

        assert source is not None
        assert source is mock_tushare
        assert hasattr(source, "fetch_calendar")

    def test_get_is_case_insensitive(self, mocker: MockerFixture) -> None:
        """Test get() normalizes case."""
        mock_tushare = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        source1 = sources.get("TUSHARE")
        source2 = sources.get("tushare")

        # Both should return valid source instances
        assert source1 is not None
        assert source2 is not None
        # Both should have the same type
        assert isinstance(source1, type(source2))
        # Both should be the same mock
        assert source1 is mock_tushare
        assert source2 is mock_tushare

    def test_get_invalid_name_raises_error(self, mocker: MockerFixture) -> None:
        """Test get() raises error for invalid source name."""
        mock_tushare = mocker.Mock()
        sources = DataSources(tushare=mock_tushare)

        with pytest.raises(ValueError, match="Unknown source"):
            sources.get("invalid_source")
