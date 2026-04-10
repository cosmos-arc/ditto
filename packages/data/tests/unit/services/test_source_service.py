"""Tests for SourceService."""

import pytest
from ditto_data.models.common import Source
from ditto_data.services.source_service import SourceService
from ditto_data.sources.source import DataSources
from pytest_mock import MockerFixture


class TestSourceService:
    """Tests for SourceService."""

    def test_get_source_by_name_string(self, mocker: MockerFixture) -> None:
        """Test get_source() method with string name returns DataSource."""
        mock_tushare = mocker.Mock()
        mock_tushare.fetch_calendar = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        service = SourceService(sources=sources)

        source = service.get_source("tushare")

        assert source is not None
        assert source is mock_tushare
        assert hasattr(source, "fetch_calendar")

    def test_get_source_by_name_enum(self, mocker: MockerFixture) -> None:
        """Test get_source() method with Source enum returns DataSource."""
        mock_tushare = mocker.Mock()
        mock_tushare.fetch_calendar = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        service = SourceService(sources=sources)

        source = service.get_source(Source.TUSHARE)

        assert source is not None
        assert source is mock_tushare

    def test_get_source_is_case_insensitive(self, mocker: MockerFixture) -> None:
        """Test get_source() normalizes case for string input."""
        mock_tushare = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        service = SourceService(sources=sources)

        source1 = service.get_source("TUSHARE")
        source2 = service.get_source("tushare")

        assert source1 is not None
        assert source2 is not None
        assert source1 is mock_tushare
        assert source2 is mock_tushare

    def test_get_source_invalid_name_raises_error(self, mocker: MockerFixture) -> None:
        """Test get_source() raises error for invalid source name."""
        mock_tushare = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        service = SourceService(sources=sources)

        with pytest.raises(ValueError, match="Unknown source"):
            service.get_source("invalid_source")

    def test_tushare_property(self, mocker: MockerFixture) -> None:
        """Test tushare property returns TushareSource instance."""
        mock_tushare = mocker.Mock()
        mock_tushare.fetch_calendar = mocker.Mock()

        sources = DataSources(tushare=mock_tushare)
        service = SourceService(sources=sources)

        source = service.tushare

        assert source is not None
        assert source is mock_tushare
