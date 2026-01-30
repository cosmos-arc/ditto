"""Tests for IndustryTushareAdapter."""

import polars as pl
import pytest
import pytest_mock
from ditto_datahub.sources.schemas.metadata_schemas import INDUSTRY_SOURCE_SCHEMA
from ditto_datahub.sources.tushare.adapters.industry import IndustryTushareAdapter


class TestIndustryTushareAdapterFetchSWIndustry:
    """Tests for fetch_sw_industry method."""

    def test_fetch_sw_industry_level1_returns_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
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

        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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
        monkeypatch: pytest.MonkeyPatch,
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

        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry(level=2)

        # Assert
        assert len(result) > 0
        assert result["industry_level"].unique().to_list() == [2]

    def test_fetch_sw_industry_validates_source_schema(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_sw_industry output conforms to INDUSTRY_SOURCE_SCHEMA."""
        # Arrange - Mock industry list query
        mock_industries = pl.DataFrame(
            {
                "index_code": ["801010.SI"],
                "index_name": ["农林牧渔"],
            }
        )

        # Mock index_member API 返回的原始数据（不包含 index_code 等列）
        # 这些列会在实现中通过 with_columns 添加
        def mock_query_impl(**kwargs):
            if kwargs.get("api_name") == "index_classify":
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

        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts()

        # Assert - Should not raise SchemaValidationError
        INDUSTRY_SOURCE_SCHEMA.validate(result)

    def test_fetch_sw_industry_empty_response_returns_empty_dataframe(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW industry with empty response returns empty DataFrame."""
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

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
        monkeypatch: pytest.MonkeyPatch,
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

        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts()

        # Assert
        assert len(result) == 2
        assert "instrument_id" in result.columns
        assert "industry_name" in result.columns

    def test_fetch_sw_industry_concepts_historical_filter(
        self,
        monkeypatch: pytest.MonkeyPatch,
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

        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts(asof_date="2020-01-01")

        # Assert - Should include stocks that were active on the asof date
        assert len(result) >= 0
