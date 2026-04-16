"""Tests for FundamentalService int instrument_id migration.

Verify that FundamentalService and its readers accept `int` instrument_id
and correctly pass it through the call chain.
"""

from datetime import date

import polars as pl
import pytest
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.ports import FundamentalReadPorts, FundamentalWritePorts
from pytest_mock import MockerFixture


def _make_service(
    mocker: MockerFixture,
    **override_readers: object,
) -> FundamentalService:
    """Create a FundamentalService with mocked dependencies."""
    mock_reader = mocker.Mock()
    readers = {
        "balance_sheet": override_readers.get("balance_sheet", mock_reader),
        "income_statement": override_readers.get("income_statement", mock_reader),
        "cash_flow": override_readers.get("cash_flow", mock_reader),
        "dividend": override_readers.get("dividend", mock_reader),
        "corporate_actions": override_readers.get("corporate_actions", mock_reader),
        "forecast": override_readers.get("forecast", mock_reader),
        "express": override_readers.get("express", mock_reader),
    }

    read_ports = FundamentalReadPorts(**readers)
    write_ports = FundamentalWritePorts(
        balance_sheet=mocker.Mock(),
        income_statement=mocker.Mock(),
        cash_flow=mocker.Mock(),
        dividend=mocker.Mock(),
        corporate_actions=mocker.Mock(),
        forecast=mocker.Mock(),
        express=mocker.Mock(),
    )
    return FundamentalService(read_ports=read_ports, write_ports=write_ports)


@pytest.mark.unit
class TestFundamentalServiceIntInstrumentId:
    """Verify FundamentalService get_* methods accept int instrument_id."""

    def test_get_balance_sheet_accepts_int(self, mocker: MockerFixture) -> None:
        """get_balance_sheet should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"instrument_id": [1_000_001], "total_assets": [1000000.0]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, balance_sheet=mock_reader)
        result = service.get_balance_sheet(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_get_income_statement_accepts_int(self, mocker: MockerFixture) -> None:
        """get_income_statement should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"instrument_id": [1_000_001], "revenue": [500000.0]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, income_statement=mock_reader)
        result = service.get_income_statement(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_get_cash_flow_accepts_int(self, mocker: MockerFixture) -> None:
        """get_cash_flow should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"instrument_id": [1_000_001], "operating_cash_flow": [200000.0]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, cash_flow=mock_reader)
        result = service.get_cash_flow(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_get_dividend_accepts_int(self, mocker: MockerFixture) -> None:
        """get_dividend should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"instrument_id": [1_000_001], "dividend_per_share": [0.5]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, dividend=mock_reader)
        result = service.get_dividend(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_get_forecast_accepts_int(self, mocker: MockerFixture) -> None:
        """get_forecast should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"instrument_id": [1_000_001], "profit_range_min": [100]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, forecast=mock_reader)
        result = service.get_forecast(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_get_express_accepts_int(self, mocker: MockerFixture) -> None:
        """get_express should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"instrument_id": [1_000_001], "type": ["express"]})
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, express=mock_reader)
        result = service.get_express(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_list_corporate_actions_accepts_int(self, mocker: MockerFixture) -> None:
        """list_corporate_actions should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"instrument_id": [1_000_001], "action_type": ["split"]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, corporate_actions=mock_reader)
        result = service.list_corporate_actions(
            instrument_id=1_000_001,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(
            1_000_001, date(2024, 1, 1), date(2024, 3, 31), None
        )

    def test_get_balance_sheet_returns_none_when_empty(
        self, mocker: MockerFixture
    ) -> None:
        """get_balance_sheet should return None when reader returns empty DF."""
        mock_reader = mocker.Mock()
        mock_reader.get.return_value = pl.DataFrame()

        service = _make_service(mocker, balance_sheet=mock_reader)
        result = service.get_balance_sheet(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert result is None
