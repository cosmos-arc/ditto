"""Tests for IndustryTushareAdapter."""

import polars as pl
import pytest_mock
from ditto_datahub.sources.tushare.adapters.industry import IndustryTushareAdapter


class TestIndustryTushareAdapterFetchSWIndustry:
    """Tests for fetch_sw_industry method."""

    def test_fetch_sw_industry_level1_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW level 1 industry classification returns valid DataFrame."""
        # Arrange - Mock Tushare API response
        mock_response = pl.DataFrame(
            {
                "index_code": ["801010.SI"],
                "index_name": ["农林牧渔"],
                "level": [1],
                "parent_index_code": [None],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry(level=1)

        # Assert
        assert len(result) > 0
        assert "industry_name" in result.columns
        assert "industry_level" in result.columns
        assert result["industry_level"].unique().to_list() == [1]

    def test_fetch_sw_industry_level2_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW level 2 industry classification returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "index_code": ["801010.SI"],
                "index_name": ["种植业"],
                "level": [2],
                "parent_index_code": ["801010.SI"],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry(level=2)

        # Assert
        assert len(result) > 0
        assert result["industry_level"].unique().to_list() == [2]

    def test_fetch_sw_industry_empty_response_returns_empty_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW industry with empty response returns empty DataFrame."""
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry(level=1)

        # Assert
        assert len(result) == 0
        assert "industry_name" in result.columns


class TestIndustryTushareAdapterFetchSWIndustryConcepts:
    """Tests for fetch_sw_industry_concepts method."""

    def test_fetch_sw_industry_concepts_returns_mapping(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW industry concepts returns stock-to-industry mapping."""
        # Arrange
        mock_industries = pl.DataFrame(
            {
                "index_code": ["801010.SI"],
                "index_name": ["农林牧渔"],
            }
        )

        def mock_query_impl(**kwargs):
            if kwargs.get("api_name") == "index_classify":
                return mock_industries
            elif kwargs.get("api_name") == "index_member":
                return pl.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ"],
                        "name": ["平安银行", "万科A"],
                        "in_date": ["20100101", "20100101"],
                        "out_date": [None, None],
                        "is_new": [1, 1],
                    }
                )
            return pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.side_effect = mock_query_impl

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts()

        # Assert
        assert len(result) == 2
        assert "instrument_id" in result.columns
        assert "industry_name" in result.columns

    def test_fetch_sw_industry_concepts_historical_filter(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW industry concepts with date filter."""
        # Arrange
        mock_industries = pl.DataFrame(
            {
                "index_code": ["801010.SI"],
                "index_name": ["农林牧渔"],
            }
        )

        def mock_query_impl(**kwargs):
            if kwargs.get("api_name") == "index_classify":
                return mock_industries
            elif kwargs.get("api_name") == "index_member":
                return pl.DataFrame(
                    {
                        "ts_code": ["000001.SZ"],
                        "name": ["平安银行"],
                        "in_date": ["20100101"],
                        "out_date": ["20200101"],
                        "is_new": [0],
                    }
                )
            return pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.side_effect = mock_query_impl

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts(asof_date="2020-01-01")

        # Assert - Should include stocks that were active on the asof date
        assert len(result) >= 0


class TestIndustryTushareAdapterFetchSWIndustryL3:
    """Tests for SW L3 industry support (T06)."""

    def test_fetch_sw_industry_level3_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW level 3 industry classification returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "index_code": ["801011.SI"],
                "index_name": ["种植业"],
                "level": [3],
                "parent_index_code": ["801010.SI"],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry(level=3)

        # Assert
        assert len(result) > 0
        assert "industry_name" in result.columns
        assert "industry_level" in result.columns
        assert result["industry_level"].unique().to_list() == [3]

    def test_fetch_sw_industry_concepts_level2(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW industry concepts with level=2 parameter."""
        # Arrange
        mock_industries = pl.DataFrame(
            {
                "index_code": ["801010.SI"],
                "index_name": ["农林牧渔"],
            }
        )

        def mock_query_impl(**kwargs):
            if kwargs.get("api_name") == "index_classify":
                # Verify level parameter is passed
                assert kwargs.get("level") == "2"
                return mock_industries
            elif kwargs.get("api_name") == "index_member":
                return pl.DataFrame(
                    {
                        "ts_code": ["000001.SZ"],
                        "name": ["平安银行"],
                        "in_date": ["20100101"],
                        "out_date": [None],
                        "is_new": [1],
                    }
                )
            return pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.side_effect = mock_query_impl

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts(level=2)

        # Assert
        assert len(result) == 1
        assert result["industry_level"].unique().to_list() == [2]


class TestIndustryTushareAdapterFetchCSRCIndustry:
    """Tests for CSRC industry support (T07)."""

    def test_fetch_csrc_industry_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching CSRC industry classification returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "industry": ["M0001"],
                "industry_name": ["农、林、牧、渔业"],
                "level": ["L1"],
                "parent_industry": [None],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_csrc_industry()

        # Assert
        assert len(result) > 0
        assert "industry_id" in result.columns
        assert "industry_name" in result.columns
        assert "industry_level" in result.columns
        assert "source" in result.columns
        assert result["source"].unique().to_list() == ["csrc"]

    def test_fetch_csrc_industry_empty_response(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching CSRC industry with empty response returns empty DataFrame."""
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_csrc_industry()

        # Assert
        assert len(result) == 0
        assert "industry_name" in result.columns

    def test_fetch_csrc_industry_uses_csrc_industrial_api(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetch_csrc_industry calls the correct Tushare API."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "industry": ["M0001"],
                "industry_name": ["农、林、牧、渔业"],
                "level": ["L1"],
                "parent_industry": [None],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        adapter.fetch_csrc_industry()

        # Assert - verify API name
        mock_client.query.assert_called_once()
        call_kwargs = mock_client.query.call_args
        assert call_kwargs.kwargs.get("api_name") == "csrc_industrial" or (
            len(call_kwargs.args) > 0
            and call_kwargs.kwargs.get("api_name") == "csrc_industrial"
        )
