"""Unit tests for FundamentalService."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.ports import FundamentalReadPorts, FundamentalWritePorts


class TestFundamentalServiceGetMethods:
    """Test get_* methods (PIT queries)."""

    @pytest.fixture
    def mock_readers(self) -> dict[str, MagicMock]:
        """Create mock readers."""
        return {
            "balance_sheet": MagicMock(),
            "income_statement": MagicMock(),
            "cash_flow": MagicMock(),
            "dividend": MagicMock(),
            "corporate_actions": MagicMock(),
            "forecast": MagicMock(),
            "express": MagicMock(),
        }

    @pytest.fixture
    def mock_writers(self) -> dict[str, MagicMock]:
        """Create mock writers."""
        return {
            "balance_sheet": MagicMock(),
            "income_statement": MagicMock(),
            "cash_flow": MagicMock(),
            "dividend": MagicMock(),
            "corporate_actions": MagicMock(),
            "forecast": MagicMock(),
            "express": MagicMock(),
        }

    @pytest.fixture
    def service(
        self,
        mock_readers: dict[str, MagicMock],
        mock_writers: dict[str, MagicMock],
    ) -> FundamentalService:
        """Create FundamentalService with mocked dependencies."""
        read_ports = FundamentalReadPorts(
            balance_sheet=mock_readers["balance_sheet"],
            income_statement=mock_readers["income_statement"],
            cash_flow=mock_readers["cash_flow"],
            dividend=mock_readers["dividend"],
            corporate_actions=mock_readers["corporate_actions"],
            forecast=mock_readers["forecast"],
            express=mock_readers["express"],
        )

        write_ports = FundamentalWritePorts(
            balance_sheet=mock_writers["balance_sheet"],
            income_statement=mock_writers["income_statement"],
            cash_flow=mock_writers["cash_flow"],
            dividend=mock_writers["dividend"],
            corporate_actions=mock_writers["corporate_actions"],
            forecast=mock_writers["forecast"],
            express=mock_writers["express"],
        )

        return FundamentalService(
            read_ports=read_ports,
            write_ports=write_ports,
        )

    def test_get_balance_sheet_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_balance_sheet returns DataFrame when data exists."""
        test_df = pl.DataFrame({"instrument_id": ["000001.SZ"], "total_assets": [1000]})
        mock_readers["balance_sheet"].get.return_value = test_df

        result = service.get_balance_sheet("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)
        mock_readers["balance_sheet"].get.assert_called_once_with(
            "000001.SZ", date(2024, 1, 1)
        )

    def test_get_balance_sheet_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_balance_sheet returns None when no data found."""
        mock_readers["balance_sheet"].get.return_value = pl.DataFrame()

        result = service.get_balance_sheet("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_income_statement_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_income_statement returns DataFrame when data exists."""
        test_df = pl.DataFrame({"instrument_id": ["000001.SZ"], "revenue": [500]})
        mock_readers["income_statement"].get.return_value = test_df

        result = service.get_income_statement("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_income_statement_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_income_statement returns None when no data found."""
        mock_readers["income_statement"].get.return_value = pl.DataFrame()

        result = service.get_income_statement("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_cash_flow_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_cash_flow returns DataFrame when data exists."""
        test_df = pl.DataFrame(
            {"instrument_id": ["000001.SZ"], "operating_cash_flow": [200]}
        )
        mock_readers["cash_flow"].get.return_value = test_df

        result = service.get_cash_flow("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_cash_flow_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_cash_flow returns None when no data found."""
        mock_readers["cash_flow"].get.return_value = pl.DataFrame()

        result = service.get_cash_flow("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_dividend_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_dividend returns DataFrame when data exists."""
        test_df = pl.DataFrame(
            {"instrument_id": ["000001.SZ"], "dividend_per_share": [0.5]}
        )
        mock_readers["dividend"].get.return_value = test_df

        result = service.get_dividend("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_dividend_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_dividend returns None when no data found."""
        mock_readers["dividend"].get.return_value = pl.DataFrame()

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
        mock_readers["forecast"].get.return_value = test_df

        result = service.get_forecast("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_forecast_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_forecast returns None when no data found."""
        mock_readers["forecast"].get.return_value = pl.DataFrame()

        result = service.get_forecast("000001.SZ", date(2024, 1, 1))

        assert result is None

    def test_get_express_returns_data_when_found(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_express returns DataFrame when data exists."""
        test_df = pl.DataFrame(
            {"instrument_id": ["000001.SZ"], "report_type": ["快报"]}
        )
        mock_readers["express"].get.return_value = test_df

        result = service.get_express("000001.SZ", date(2024, 1, 1))

        assert result is not None
        assert result.equals(test_df)

    def test_get_express_returns_none_when_empty(
        self, service: FundamentalService, mock_readers: dict[str, MagicMock]
    ) -> None:
        """Test get_express returns None when no data found."""
        mock_readers["express"].get.return_value = pl.DataFrame()

        result = service.get_express("000001.SZ", date(2024, 1, 1))

        assert result is None


class TestFundamentalServiceListMethods:
    """Test list_* methods."""

    def test_list_corporate_actions(self) -> None:
        """Test list_corporate_actions returns DataFrame."""
        corporate_actions_reader = MagicMock()
        mock_reader = MagicMock()
        mock_writer = MagicMock()

        read_ports = FundamentalReadPorts(
            balance_sheet=mock_reader,
            income_statement=mock_reader,
            cash_flow=mock_reader,
            dividend=mock_reader,
            corporate_actions=corporate_actions_reader,
            forecast=mock_reader,
            express=mock_reader,
        )

        write_ports = FundamentalWritePorts(
            balance_sheet=mock_writer,
            income_statement=mock_writer,
            cash_flow=mock_writer,
            dividend=mock_writer,
            corporate_actions=mock_writer,
            forecast=mock_writer,
            express=mock_writer,
        )

        service = FundamentalService(
            read_ports=read_ports,
            write_ports=write_ports,
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

        read_ports = FundamentalReadPorts(
            balance_sheet=mock_reader,
            income_statement=mock_reader,
            cash_flow=mock_reader,
            dividend=mock_reader,
            corporate_actions=mock_reader,
            forecast=mock_reader,
            express=mock_reader,
        )

        write_ports = FundamentalWritePorts(
            balance_sheet=mock_writer,
            income_statement=mock_writer,
            cash_flow=mock_writer,
            dividend=mock_writer,
            corporate_actions=mock_writer,
            forecast=mock_writer,
            express=mock_writer,
        )

        return FundamentalService(
            read_ports=read_ports,
            write_ports=write_ports,
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
        service._write_ports.balance_sheet.write.assert_called_once_with(sample_df)

    def test_save_income_statement(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_income_statement calls writer and returns count."""
        result = service.save_income_statement(sample_df)

        assert result == 5
        service._write_ports.income_statement.write.assert_called_once_with(sample_df)

    def test_save_cash_flow(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_cash_flow calls writer and returns count."""
        result = service.save_cash_flow(sample_df)

        assert result == 5
        service._write_ports.cash_flow.write.assert_called_once_with(sample_df)

    def test_save_dividend(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_dividend calls writer and returns count."""
        result = service.save_dividend(sample_df)

        assert result == 5
        service._write_ports.dividend.write.assert_called_once_with(sample_df)

    def test_save_corporate_actions(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_corporate_actions calls writer and returns count."""
        result = service.save_corporate_actions(sample_df)

        assert result == 5
        service._write_ports.corporate_actions.write.assert_called_once_with(sample_df)

    def test_save_forecast(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_forecast calls writer and returns count."""
        result = service.save_forecast(sample_df)

        assert result == 5
        service._write_ports.forecast.write.assert_called_once_with(sample_df)

    def test_save_express(
        self, service: FundamentalService, sample_df: pl.DataFrame
    ) -> None:
        """Test save_express calls writer and returns count."""
        result = service.save_express(sample_df)

        assert result == 5
        service._write_ports.express.write.assert_called_once_with(sample_df)
