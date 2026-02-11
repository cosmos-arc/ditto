"""Unit tests for FundamentalService."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.fundamental_service import FundamentalService


class TestFundamentalServiceGetMethods:
    """Test get_* methods (PIT queries)."""

    @pytest.fixture
    def mock_readers(self) -> dict[str, MagicMock]:
        """Create mock readers."""
        return {
            "balance_sheet_reader": MagicMock(),
            "income_statement_reader": MagicMock(),
            "cash_flow_reader": MagicMock(),
            "dividend_reader": MagicMock(),
            "forecast_reader": MagicMock(),
            "express_reader": MagicMock(),
        }

    @pytest.fixture
    def mock_writers(self) -> dict[str, MagicMock]:
        """Create mock writers."""
        return {
            "balance_sheet_writer": MagicMock(),
            "income_statement_writer": MagicMock(),
            "cash_flow_writer": MagicMock(),
            "dividend_writer": MagicMock(),
            "corporate_actions_writer": MagicMock(),
            "forecast_writer": MagicMock(),
            "express_writer": MagicMock(),
        }

    @pytest.fixture
    def corporate_actions_reader(self) -> MagicMock:
        """Create mock corporate actions reader."""
        return MagicMock()

    @pytest.fixture
    def corporate_actions_writer(self) -> MagicMock:
        """Create mock corporate actions writer."""
        return MagicMock()

    @pytest.fixture
    def service(
        self,
        mock_readers: dict[str, MagicMock],
        mock_writers: dict[str, MagicMock],
        corporate_actions_reader: MagicMock,
        corporate_actions_writer: MagicMock,
    ) -> FundamentalService:
        """Create FundamentalService with mocked dependencies."""
        return FundamentalService(
            balance_sheet_reader=mock_readers["balance_sheet_reader"],
            balance_sheet_writer=mock_writers["balance_sheet_writer"],
            income_statement_reader=mock_readers["income_statement_reader"],
            income_statement_writer=mock_writers["income_statement_writer"],
            cash_flow_reader=mock_readers["cash_flow_reader"],
            cash_flow_writer=mock_writers["cash_flow_writer"],
            dividend_reader=mock_readers["dividend_reader"],
            dividend_writer=mock_writers["dividend_writer"],
            corporate_actions_reader=corporate_actions_reader,
            corporate_actions_writer=corporate_actions_writer,
            forecast_reader=mock_readers["forecast_reader"],
            forecast_writer=mock_writers["forecast_writer"],
            express_reader=mock_readers["express_reader"],
            express_writer=mock_writers["express_writer"],
        )

    def test_get_balance_sheet_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_balance_sheet returns DataFrame when data exists."""
        test_df = pl.DataFrame({"instrument_id": ["000001.SZ"], "total_assets": [1000]})
        mock_readers["balance_sheet_reader"].get.return_value = test_df

        result = service.get_balance_sheet("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)
        mock_readers["balance_sheet_reader"].get.assert_called_once_with(
            "000001.SZ", date(2024, 1, 1)
        )

    def test_get_balance_sheet_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_balance_sheet returns None when no data found."""
        mock_readers["balance_sheet_reader"].get.return_value = pl.DataFrame()

        result = service.get_balance_sheet("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_income_statement_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_income_statement returns DataFrame when data exists."""
        test_df = pl.DataFrame({"instrument_id": ["000001.SZ"], "revenue": [500]})
        mock_readers["income_statement_reader"].get.return_value = test_df

        result = service.get_income_statement("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_income_statement_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_income_statement returns None when no data found."""
        mock_readers["income_statement_reader"].get.return_value = pl.DataFrame()

        result = service.get_income_statement("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_cash_flow_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_cash_flow returns DataFrame when data exists."""
        test_df = pl.DataFrame(
            {"instrument_id": ["000001.SZ"], "operating_cash_flow": [200]}
        )
        mock_readers["cash_flow_reader"].get.return_value = test_df

        result = service.get_cash_flow("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_cash_flow_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_cash_flow returns None when no data found."""
        mock_readers["cash_flow_reader"].get.return_value = pl.DataFrame()

        result = service.get_cash_flow("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_dividend_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_dividend returns DataFrame when data exists."""
        test_df = pl.DataFrame(
            {"instrument_id": ["000001.SZ"], "dividend_per_share": [0.5]}
        )
        mock_readers["dividend_reader"].get.return_value = test_df

        result = service.get_dividend("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_dividend_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_dividend returns None when no data found."""
        mock_readers["dividend_reader"].get.return_value = pl.DataFrame()

        result = service.get_dividend("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_forecast_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_forecast returns DataFrame when data exists."""
        test_df = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "profit_range_min": [100],
                "profit_range_max": [150],
            }
        )
        mock_readers["forecast_reader"].get.return_value = test_df

        result = service.get_forecast("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_forecast_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_forecast returns None when no data found."""
        mock_readers["forecast_reader"].get.return_value = pl.DataFrame()

        result = service.get_forecast("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_express_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_express returns DataFrame when data exists."""
        test_df = pl.DataFrame(
            {"instrument_id": ["000001.SZ"], "report_type": ["快报"]}
        )
        mock_readers["express_reader"].get.return_value = test_df

        result = service.get_express("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_express_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_express returns None when no data found."""
        mock_readers["express_reader"].get.return_value = pl.DataFrame()

        result = service.get_express("000001.SZ", date(2024, 1, 1))

        assert result is None


class TestFundamentalServiceListMethods:
    """Test list_* methods."""

    def test_list_corporate_actions(self) -> None:
        """Test list_corporate_actions returns DataFrame."""
        corporate_actions_reader = MagicMock()
        corporate_actions_writer = MagicMock()
        mock_reader = MagicMock()
        mock_writer = MagicMock()

        service = FundamentalService(
            balance_sheet_reader=mock_reader,
            balance_sheet_writer=mock_writer,
            income_statement_reader=mock_reader,
            income_statement_writer=mock_writer,
            cash_flow_reader=mock_reader,
            cash_flow_writer=mock_writer,
            dividend_reader=mock_reader,
            dividend_writer=mock_writer,
            corporate_actions_reader=corporate_actions_reader,
            corporate_actions_writer=corporate_actions_writer,
            forecast_reader=mock_reader,
            forecast_writer=mock_writer,
            express_reader=mock_reader,
            express_writer=mock_writer,
        )

        test_df = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "action_type": ["分红"],
                "announcement_date": [date(2024, 1, 1)],
            }
        )
        corporate_actions_reader.get.return_value = test_df

        result = service.list_corporate_actions(
            "000001.SZ", date(2024, 1, 1), date(2024, 1, 31)
        )

        assert result.equals(test_df)
        corporate_actions_reader.get.assert_called_once_with(
            "000001.SZ", date(2024, 1, 1), date(2024, 1, 31)
        )


class TestFundamentalServiceSaveMethods:
    """Test save_* methods."""

    @pytest.fixture
    def service(self) -> FundamentalService:
        """Create FundamentalService with mocked dependencies."""
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.write.return_value = 5  # Simulate 5 records written
        return FundamentalService(
            balance_sheet_reader=mock_reader,
            balance_sheet_writer=mock_writer,
            income_statement_reader=mock_reader,
            income_statement_writer=mock_writer,
            cash_flow_reader=mock_reader,
            cash_flow_writer=mock_writer,
            dividend_reader=mock_reader,
            dividend_writer=mock_writer,
            corporate_actions_reader=mock_reader,
            corporate_actions_writer=mock_writer,
            forecast_reader=mock_reader,
            forecast_writer=mock_writer,
            express_reader=mock_reader,
            express_writer=mock_writer,
        )

    @pytest.fixture
    def sample_df(self) -> pl.DataFrame:
        """Create sample DataFrame for testing."""
        return pl.DataFrame({"instrument_id": ["000001.SZ"], "value": [100]})

    def test_save_balance_sheet(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_balance_sheet calls writer and returns count."""
        result = service.save_balance_sheet(sample_df)

        assert result == 5
        service._balance_sheet_writer.write.assert_called_once_with(sample_df)

    def test_save_income_statement(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_income_statement calls writer and returns count."""
        result = service.save_income_statement(sample_df)

        assert result == 5
        service._income_statement_writer.write.assert_called_once_with(sample_df)

    def test_save_cash_flow(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_cash_flow calls writer and returns count."""
        result = service.save_cash_flow(sample_df)

        assert result == 5
        service._cash_flow_writer.write.assert_called_once_with(sample_df)

    def test_save_dividend(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_dividend calls writer and returns count."""
        result = service.save_dividend(sample_df)

        assert result == 5
        service._dividend_writer.write.assert_called_once_with(sample_df)

    def test_save_corporate_actions(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_corporate_actions calls writer and returns count."""
        result = service.save_corporate_actions(sample_df)

        assert result == 5
        service._corporate_actions_writer.write.assert_called_once_with(sample_df)

    def test_save_forecast(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_forecast calls writer and returns count."""
        result = service.save_forecast(sample_df)

        assert result == 5
        service._forecast_writer.write.assert_called_once_with(sample_df)

    def test_save_express(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_express calls writer and returns count."""
        result = service.save_express(sample_df)

        assert result == 5
        service._express_writer.write.assert_called_once_with(sample_df)
