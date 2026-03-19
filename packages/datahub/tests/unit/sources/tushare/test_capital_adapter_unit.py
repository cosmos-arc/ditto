"""Tests for CapitalTushareAdapter."""

import polars as pl
import pytest_mock
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter


class TestCapitalTushareAdapterFetchValuationMetrics:
    """Tests for fetch_valuation_metrics method."""

    def test_fetch_valuation_metrics_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching valuation metrics returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "pe": [10.5],
                "pb": [1.2],
                "ps": [2.3],
                "dv_ratio": [0.03],  # API returns dv_ratio, not dividend_yield
                "total_mv": [1000000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_valuation_metrics(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "trade_date" in result.columns
        assert "pe_ratio" in result.columns
        assert "pb_ratio" in result.columns
        assert result["source_ticker"][0] == "000001.SZ"

    def test_fetch_valuation_metrics_empty_response_returns_empty_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """
        Test fetching valuation metrics with empty response returns empty
        DataFrame.
        """
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_valuation_metrics(ts_code="000001.SZ")

        # Assert
        assert len(result) == 0
        assert "source_ticker" in result.columns


class TestCapitalTushareAdapterFetchDividend:
    """Tests for fetch_dividend method."""

    def test_fetch_dividend_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching dividend data returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ex_date": ["20240101"],
                "cash_div": [0.5],  # API returns cash_div
                "record_date": ["20240102"],
                "ann_date": ["20240101"],
                "div_proc": ["实施"],  # P015: 实施进度
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_dividend(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "ex_dividend_date" in result.columns
        assert "dividend_per_share" in result.columns
        assert "div_proc" in result.columns  # P015: 验证实施进度字段


class TestCapitalTushareAdapterFetchMarginTrading:
    """Tests for fetch_margin_trading method."""

    def test_fetch_margin_trading_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching margin trading data returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "rzye": [100000.0],  # 融资余额
                "rzmre": [1000.0],  # 融资买入量
                "rqye": [50000.0],  # 融券余额
                "rqmcl": [500.0],  # 融券卖出量
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_margin_trading(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "margin_buy_balance" in result.columns
        assert "short_sell_balance" in result.columns


class TestCapitalTushareAdapterFetchPledgeRatio:
    """Tests for fetch_pledge_ratio method."""

    def test_fetch_pledge_ratio_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching pledge ratio data returns valid DataFrame."""
        # Arrange - Mock Tushare API response (using actual API field names)
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20240101"],  # Required for date conversion
                "pledge_ratio": [5.5],
                "total_share": [10000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_pledge_ratio(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "pledge_ratio" in result.columns
        assert "total_shares" in result.columns


class TestCapitalTushareAdapterFetchIndexComposition:
    """Tests for fetch_index_composition method."""

    def test_fetch_index_composition_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching index composition returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ"],
                "in_date": ["20200101", "20200101"],
                "out_date": ["", ""],
                "is_new": [1, 1],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_index_composition(index_code="000001.SH")

        # Assert
        assert len(result) == 2
        assert "index_id" in result.columns
        assert "source_ticker" in result.columns
        assert "effective_from" in result.columns


class TestCapitalTushareAdapterFetchCorporateActions:
    """Tests for fetch_corporate_actions method."""

    def test_fetch_corporate_actions_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching corporate actions returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240101"],
                "act_date": ["20240115"],
                "ba_type": ["分红"],
                "name": ["2023年度分红"],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_corporate_actions(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "action_type" in result.columns
        assert "announcement_date" in result.columns
