"""Tests for CapitalTushareAdapter."""

import polars as pl
import pytest_mock
from ditto_datahub.sources.schemas.capital_schemas import (
    BALANCE_SHEET_SOURCE_SCHEMA,
    CASH_FLOW_SOURCE_SCHEMA,
    CORPORATE_ACTIONS_SOURCE_SCHEMA,
    DIVIDEND_SOURCE_SCHEMA,
    FUTURES_SOURCE_SCHEMA,
    INCOME_STATEMENT_SOURCE_SCHEMA,
    INDEX_COMPOSITION_SOURCE_SCHEMA,
    MARGIN_TRADING_SOURCE_SCHEMA,
    PLEDGE_RATIO_SOURCE_SCHEMA,
    VALUATION_METRICS_SOURCE_SCHEMA,
)
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter


class TestCapitalTushareAdapterFetchValuationMetrics:
    """Tests for fetch_valuation_metrics method."""

    def test_fetch_valuation_metrics_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching valuation metrics returns valid DataFrame."""
        # Arrange - Mock Tushare API response
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "pe": [10.5],
                "pb": [1.2],
                "ps": [2.3],
                "dividend_yield": [0.03],
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
        assert "instrument_id" in result.columns
        assert "trade_date" in result.columns
        assert "pe_ratio" in result.columns
        assert "pb_ratio" in result.columns
        assert result["instrument_id"][0] == "000001.SZ"

    def test_fetch_valuation_metrics_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_valuation_metrics output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "pe": [10.5],
                "pb": [1.2],
                "ps": [2.3],
                "dividend_yield": [0.03],
                "total_mv": [1000000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_valuation_metrics(ts_code="000001.SZ")

        # Assert - Should not raise SchemaValidationError
        VALUATION_METRICS_SOURCE_SCHEMA.validate(result)

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
        assert "instrument_id" in result.columns


class TestCapitalTushareAdapterFetchDividend:
    """Tests for fetch_dividend method."""

    def test_fetch_dividend_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching dividend data returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ex_date": ["20240101"],
                "dividend": [0.5],
                "dividend_yield": [0.03],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_dividend(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "instrument_id" in result.columns
        assert "ex_dividend_date" in result.columns
        assert "dividend_per_share" in result.columns

    def test_fetch_dividend_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_dividend output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ex_date": ["20240101"],
                "dividend": [0.5],
                "dividend_yield": [0.03],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_dividend(ts_code="000001.SZ")

        # Assert - Should not raise SchemaValidationError
        DIVIDEND_SOURCE_SCHEMA.validate(result)


class TestCapitalTushareAdapterFetchMarginTrading:
    """Tests for fetch_margin_trading method."""

    def test_fetch_margin_trading_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching margin trading data returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "rz_balance": [100000.0],
                "rz_vol": [1000.0],
                "rq_balance": [50000.0],
                "rq_vol": [500.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_margin_trading(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "instrument_id" in result.columns
        assert "margin_buy_balance" in result.columns
        assert "short_sell_balance" in result.columns

    def test_fetch_margin_trading_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_margin_trading output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240101"],
                "rz_balance": [100000.0],
                "rz_vol": [1000.0],
                "rq_balance": [50000.0],
                "rq_vol": [500.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_margin_trading(ts_code="000001.SZ")

        # Assert - Should not raise SchemaValidationError
        MARGIN_TRADING_SOURCE_SCHEMA.validate(result)


class TestCapitalTushareAdapterFetchPledgeRatio:
    """Tests for fetch_pledge_ratio method."""

    def test_fetch_pledge_ratio_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching pledge ratio data returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "pledge_ratio": [5.5],
                "pledge_count": [1000000.0],
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
        assert "instrument_id" in result.columns
        assert "pledge_ratio" in result.columns
        assert "pledge_shares" in result.columns

    def test_fetch_pledge_ratio_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_pledge_ratio output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "pledge_ratio": [5.5],
                "pledge_count": [1000000.0],
                "total_share": [10000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_pledge_ratio(ts_code="000001.SZ")

        # Assert - Should not raise SchemaValidationError
        PLEDGE_RATIO_SOURCE_SCHEMA.validate(result)


class TestCapitalTushareAdapterFetchFutures:
    """Tests for fetch_futures method."""

    def test_fetch_futures_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching futures data returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["IF2401"],
                "trade_date": ["20240101"],
                "oi": [10000.0],
                "settlement": [3500.0],
                "vol": [5000.0],
                "amount": [175000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_futures(ts_code="IF2401")

        # Assert
        assert len(result) > 0
        assert "instrument_id" in result.columns
        assert "open_interest" in result.columns
        assert "settlement_price" in result.columns

    def test_fetch_futures_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_futures output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["IF2401"],
                "trade_date": ["20240101"],
                "oi": [10000.0],
                "settlement": [3500.0],
                "vol": [5000.0],
                "amount": [175000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_futures(ts_code="IF2401")

        # Assert - Should not raise SchemaValidationError
        FUTURES_SOURCE_SCHEMA.validate(result)


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
        assert "instrument_id" in result.columns
        assert "effective_from" in result.columns

    def test_fetch_index_composition_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_index_composition output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "in_date": ["20200101"],
                "is_new": [1],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_index_composition(index_code="000001.SH")

        # Assert - Should not raise SchemaValidationError
        INDEX_COMPOSITION_SOURCE_SCHEMA.validate(result)


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
        assert "instrument_id" in result.columns
        assert "action_type" in result.columns
        assert "announcement_date" in result.columns

    def test_fetch_corporate_actions_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_corporate_actions output conforms to SourceSchema."""
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

        # Assert - Should not raise SchemaValidationError
        CORPORATE_ACTIONS_SOURCE_SCHEMA.validate(result)


class TestCapitalTushareAdapterFetchBalanceSheet:
    """Tests for fetch_balance_sheet method."""

    def test_fetch_balance_sheet_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching balance sheet returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20231231"],
                "ann_date": ["20240430"],
                "total_assets": [1000000000.0],
                "total_liab": [500000000.0],
                "total_hldr_eqy_exc_min_int": [500000000.0],
                "total_cur_assets": [600000000.0],
                "total_cur_liab": [300000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_balance_sheet(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "instrument_id" in result.columns
        assert "report_date" in result.columns
        assert "total_assets" in result.columns
        assert "net_assets" in result.columns

    def test_fetch_balance_sheet_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_balance_sheet output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20231231"],
                "ann_date": ["20240430"],
                "total_assets": [1000000000.0],
                "total_liab": [500000000.0],
                "total_hldr_eqy_exc_min_int": [500000000.0],
                "total_cur_assets": [600000000.0],
                "total_cur_liab": [300000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_balance_sheet(ts_code="000001.SZ")

        # Assert - Should not raise SchemaValidationError
        BALANCE_SHEET_SOURCE_SCHEMA.validate(result)


class TestCapitalTushareAdapterFetchIncomeStatement:
    """Tests for fetch_income_statement method."""

    def test_fetch_income_statement_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching income statement returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20231231"],
                "ann_date": ["20240430"],
                "total_operating_revenue": [1000000000.0],
                "operating_profit": [100000000.0],
                "net_profit": [80000000.0],
                "basic_eps": [1.5],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_income_statement(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "instrument_id" in result.columns
        assert "report_date" in result.columns
        assert "revenue" in result.columns
        assert "eps" in result.columns

    def test_fetch_income_statement_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_income_statement output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20231231"],
                "ann_date": ["20240430"],
                "total_operating_revenue": [1000000000.0],
                "operating_profit": [100000000.0],
                "net_profit": [80000000.0],
                "basic_eps": [1.5],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_income_statement(ts_code="000001.SZ")

        # Assert - Should not raise SchemaValidationError
        INCOME_STATEMENT_SOURCE_SCHEMA.validate(result)


class TestCapitalTushareAdapterFetchCashFlow:
    """Tests for fetch_cash_flow method."""

    def test_fetch_cash_flow_returns_dataframe(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test fetching cash flow statement returns valid DataFrame."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20231231"],
                "ann_date": ["20240430"],
                "n_cashflow_act": [100000000.0],
                "n_cash_flows_inv_act": [-50000000.0],
                "n_cash_flows_fnc_act": [-30000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_cash_flow(ts_code="000001.SZ")

        # Assert
        assert len(result) > 0
        assert "instrument_id" in result.columns
        assert "report_date" in result.columns
        assert "operating_cash_flow" in result.columns
        assert "net_cash_flow" in result.columns

    def test_fetch_cash_flow_validates_source_schema(
        self,
        mocker: pytest_mock.MockFixture,
    ) -> None:
        """Test that fetch_cash_flow output conforms to SourceSchema."""
        # Arrange
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "end_date": ["20231231"],
                "ann_date": ["20240430"],
                "n_cashflow_act": [100000000.0],
                "n_cash_flows_inv_act": [-50000000.0],
                "n_cash_flows_fnc_act": [-30000000.0],
            }
        )

        mock_client = mocker.Mock()
        mock_client.query.return_value = mock_response

        # Act
        adapter = CapitalTushareAdapter(_client=mock_client)
        result = adapter.fetch_cash_flow(ts_code="000001.SZ")

        # Assert - Should not raise SchemaValidationError
        CASH_FLOW_SOURCE_SCHEMA.validate(result)
