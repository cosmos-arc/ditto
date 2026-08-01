"""Tests for CapitalTushareAdapter."""

from datetime import date

import polars as pl
import pytest_mock
from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter


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

    def test_fetch_index_weight_returns_effective_dated_canonical_rows(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        mock_client = mocker.Mock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "index_code": ["000300.SH", "000300.SH"],
                "con_code": ["600000.SH", "600036.SH"],
                "trade_date": ["20241227", "20241227"],
                "weight": [60.0, 40.0],
            }
        )
        adapter = CapitalTushareAdapter(_client=mock_client)

        result = adapter.fetch_index_weight("000300.SH", "20241227")

        assert result.columns == [
            "index_code",
            "source_ticker",
            "effective_from",
            "effective_to",
            "weight",
        ]
        assert result["effective_from"].dtype == pl.Date
        assert result["effective_from"].to_list() == [
            date(2024, 12, 27),
            date(2024, 12, 27),
        ]

    def test_fetch_index_weight_supports_provider_date_range(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        mock_client = mocker.Mock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "index_code": ["000300.SH"],
                "con_code": ["600000.SH"],
                "trade_date": ["20241227"],
                "weight": [100.0],
            }
        )
        adapter = CapitalTushareAdapter(_client=mock_client)

        adapter.fetch_index_weight(
            "000300.SH",
            start_date="20240101",
            end_date="20241231",
        )

        mock_client.query.assert_called_once_with(
            api_name="index_weight",
            index_code="000300.SH",
            start_date="20240101",
            end_date="20241231",
            fields="index_code,con_code,trade_date,weight",
        )


class TestCapitalTushareAdapterFetchCorporateActions:
    """Tests for fetch_corporate_actions method."""

    def test_fetch_corporate_actions_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Normalize official repurchase and share-float endpoints together."""
        repurchase = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240101"],
                "end_date": ["20240115"],
                "proc": ["完成"],
                "exp_date": [None],
                "vol": [1_000_000.0],
                "amount": [10_000_000.0],
            }
        )
        share_float = pl.DataFrame(
            {
                "ts_code": ["000002.SZ"],
                "ann_date": ["20240102"],
                "float_date": ["20240120"],
                "float_share": [2_000_000.0],
                "float_ratio": [1.5],
                "holder_name": ["holder"],
                "share_type": ["首发原股东限售股份"],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.side_effect = [repurchase, share_float]

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_corporate_actions(
            start_date="20240101",
            end_date="20240331",
        )

        assert result["source_ticker"].to_list() == ["000001.SZ", "000002.SZ"]
        assert result["action_type"].to_list() == [
            "share_repurchase",
            "restricted_share_release",
        ]
        assert result["action_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 2),
        ]
        assert result["effective_from"].to_list() == [
            date(2024, 1, 15),
            date(2024, 1, 20),
        ]
        assert result.columns == [
            "source_ticker",
            "action_type",
            "action_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "description",
        ]
        api_names = [
            call.kwargs["api_name"] for call in mock_client.query.call_args_list
        ]
        assert api_names == [
            "repurchase",
            "share_float",
        ]

    def test_fetch_corporate_actions_fills_missing_provider_dates_without_lookahead(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Required event dates fall back only to dates observable on the row."""
        repurchase = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240101"],
                "end_date": [None],
                "proc": ["预案"],
                "exp_date": ["20240630"],
                "vol": [None],
                "amount": [None],
            }
        )
        share_float = pl.DataFrame(
            {
                "ts_code": ["000002.SZ"],
                "ann_date": [None],
                "float_date": ["20240120"],
                "float_share": [2_000_000.0],
                "float_ratio": [1.5],
                "holder_name": ["holder"],
                "share_type": ["股权分置限售股份"],
            }
        )
        mock_client = mocker.Mock()
        mock_client.query.side_effect = [repurchase, share_float]

        result = CapitalTushareAdapter(_client=mock_client).fetch_corporate_actions(
            start_date="20240101",
            end_date="20240331",
        )

        assert result["action_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 20),
        ]
        assert result["knowledge_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 20),
        ]
        assert result["effective_from"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 20),
        ]
        assert result["effective_to"].to_list() == [date(2024, 6, 30), None]


class TestCapitalTushareAdapterFetchShareBuyback:
    """Tests for fetch_share_buyback method."""

    def test_fetch_share_buyback_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching share buyback data returns valid DataFrame."""
        # Arrange - Mock Tushare share_float API response
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240101"],
                "float_date": ["20240115"],
                "float_share": [50000000.0],
                "float_ratio": [2.5],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_share_buyback(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "announcement_date" in result.columns
        assert "effective_date" in result.columns
        assert "float_shares" in result.columns
        assert "float_ratio" in result.columns

    def test_fetch_share_buyback_empty_response(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching share buyback with empty response returns empty DataFrame."""
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_share_buyback(ts_code="000001.SZ")

        # Assert
        assert len(result) == 0
        assert "source_ticker" in result.columns


class TestCapitalTushareAdapterFetchRightsIssue:
    """Tests for fetch_rights_issue method."""

    def test_fetch_rights_issue_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching rights issue data returns valid DataFrame."""
        # Arrange - Mock Tushare rights API response
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "rights_type": ["A"],
                "ann_date": ["20240101"],
                "reg_date": ["20240110"],
                "ex_date": ["20240111"],
                "rights_price": [5.0],
                "rights_ratio": [0.3],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_rights_issue(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "source_ticker" in result.columns
        assert "rights_type" in result.columns
        assert "announcement_date" in result.columns
        assert "record_date" in result.columns
        assert "ex_rights_date" in result.columns
        assert "rights_price" in result.columns
        assert "rights_ratio" in result.columns

    def test_fetch_rights_issue_empty_response(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching rights issue with empty response returns empty DataFrame."""
        # Arrange
        mock_response = pl.DataFrame()

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_rights_issue(ts_code="000001.SZ")

        # Assert
        assert len(result) == 0
        assert "source_ticker" in result.columns
