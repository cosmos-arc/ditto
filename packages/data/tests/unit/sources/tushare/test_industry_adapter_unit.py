"""Tests for IndustryTushareAdapter."""

from datetime import date

import polars as pl
import pytest_mock
from ditto_data.sources.tushare.adapters.industry import IndustryTushareAdapter


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
                "industry_name": ["农林牧渔"],
                "level": ["L1"],
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
        mock_client.query.assert_called_once_with(
            api_name="index_classify",
            level="L1",
            src="SW2021",
            fields="index_code,industry_name,level",
        )

    def test_fetch_sw_industry_level2_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW level 2 industry classification returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "index_code": ["801010.SI"],
                "industry_name": ["种植业"],
                "level": ["L2"],
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
        mock_client = mocker.Mock()
        members = pl.DataFrame(
            {
                "l1_code": ["801010.SI", "801010.SI"],
                "l1_name": ["农林牧渔", "农林牧渔"],
                "l2_code": ["801011.SI", "801011.SI"],
                "l2_name": ["种植业", "种植业"],
                "l3_code": ["850111.SI", "850111.SI"],
                "l3_name": ["种子", "种子"],
                "ts_code": ["000001.SZ", "000002.SZ"],
                "name": ["平安银行", "万科A"],
                "in_date": ["20100101", "20100101"],
                "out_date": [None, None],
                "is_new": ["Y", "Y"],
            }
        )
        mock_client.query.side_effect = [
            pl.DataFrame(
                {
                    "index_code": ["801010.SI"],
                    "industry_name": ["农林牧渔"],
                }
            ),
            members,
        ]

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts(knowledge_date=date(2026, 9, 1))

        # Assert
        assert len(result) == 2
        assert "instrument_id" in result.columns
        assert "industry_name" in result.columns
        assert result["knowledge_date"].unique().to_list() == [date(2026, 9, 1)]
        called_apis = [
            call.kwargs["api_name"] for call in mock_client.query.call_args_list
        ]
        assert called_apis == [
            "index_classify",
            "index_member_all",
        ]
        assert mock_client.query.call_args_list[1].kwargs["l1_code"] == "801010.SI"

    def test_fetch_sw_industry_concepts_historical_filter(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching SW industry concepts with date filter."""
        # Arrange
        mock_client = mocker.Mock()
        members = pl.DataFrame(
            {
                "l1_code": ["801010.SI", "801020.SI", "801030.SI"],
                "l1_name": ["农林牧渔", "采掘", "化工"],
                "l2_code": ["801011.SI", "801021.SI", "801031.SI"],
                "l2_name": ["种植业", "煤炭", "化学原料"],
                "l3_code": ["850111.SI", "850211.SI", "850311.SI"],
                "l3_name": ["种子", "煤炭开采", "无机盐"],
                "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "name": ["甲", "乙", "丙"],
                "in_date": ["20100101", "20200101", "20210101"],
                "out_date": ["20191231", None, None],
                "is_new": ["N", "Y", "Y"],
            }
        )
        mock_client.query.side_effect = [
            pl.DataFrame(
                {
                    "index_code": ["801010.SI", "801020.SI", "801030.SI"],
                    "industry_name": ["农林牧渔", "采掘", "化工"],
                }
            ),
            members.filter(pl.col("l1_code") == "801010.SI"),
            members.filter(pl.col("l1_code") == "801020.SI"),
            members.filter(pl.col("l1_code") == "801030.SI"),
        ]

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts(
            asof_date="2020-01-01",
            knowledge_date=date(2026, 9, 1),
        )

        # Only memberships effective on the requested historical date survive.
        assert result["instrument_id"].to_list() == ["000002.SZ"]
        assert result["knowledge_date"].to_list() == [date(2026, 9, 1)]
        assert all(
            "date" not in call.kwargs for call in mock_client.query.call_args_list
        )

    def test_fetch_sw_industry_concepts_rejects_provider_placeholder_tickers(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Only exchange-resolvable A-share tickers may enter mappings."""
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [
            pl.DataFrame(
                {
                    "index_code": ["801010.SI"],
                    "industry_name": ["农林牧渔"],
                }
            ),
            pl.DataFrame(
                {
                    "l1_code": ["801010.SI", "801010.SI"],
                    "l1_name": ["农林牧渔", "农林牧渔"],
                    "l2_code": ["801011.SI", "801011.SI"],
                    "l2_name": ["种植业", "种植业"],
                    "l3_code": ["850111.SI", "850111.SI"],
                    "l3_name": ["种子", "种子"],
                    "ts_code": ["000001.SZ", "T00018.SH"],
                    "name": ["平安银行", "供应商占位符"],
                    "in_date": ["20100101", "20100101"],
                    "out_date": [None, None],
                    "is_new": ["Y", "Y"],
                }
            ),
        ]

        result = IndustryTushareAdapter(_client=mock_client).fetch_sw_industry_concepts(
            knowledge_date=date(2026, 9, 1)
        )

        assert result["instrument_id"].to_list() == ["000001.SZ"]


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
                "industry_name": ["种植业"],
                "level": ["L3"],
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
        mock_client = mocker.Mock()
        members = pl.DataFrame(
            {
                "l1_code": ["801010.SI"],
                "l1_name": ["农林牧渔"],
                "l2_code": ["801011.SI"],
                "l2_name": ["种植业"],
                "l3_code": ["850111.SI"],
                "l3_name": ["种子"],
                "ts_code": ["000001.SZ"],
                "name": ["平安银行"],
                "in_date": ["20100101"],
                "out_date": [None],
                "is_new": ["Y"],
            }
        )
        mock_client.query.side_effect = [
            pl.DataFrame(
                {
                    "index_code": ["801011.SI"],
                    "industry_name": ["种植业"],
                }
            ),
            members,
        ]

        # Act
        adapter = IndustryTushareAdapter(_client=mock_client)
        result = adapter.fetch_sw_industry_concepts(
            level=2,
            knowledge_date=date(2026, 9, 1),
        )

        # Assert
        assert len(result) == 1
        assert result["industry_level"].unique().to_list() == [2]
        assert result["industry_name"].to_list() == ["种植业"]
        assert mock_client.query.call_args_list[0].kwargs["level"] == "L2"
        assert mock_client.query.call_args_list[1].kwargs["l2_code"] == "801011.SI"


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
