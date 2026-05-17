"""Tests for CapitalStore int instrument_id migration.

Verify that CapitalStore and its readers accept `int` instrument_id
and correctly pass it through the call chain.
"""

from datetime import date

import polars as pl
import pytest
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from pytest_mock import MockerFixture


def _make_service(
    mocker: MockerFixture,
    mock_margin_reader: object | None = None,
    mock_pledge_reader: object | None = None,
    mock_valuation_reader: object | None = None,
    mock_index_reader: object | None = None,
) -> CapitalStore:
    """Create a CapitalStore with mocked dependencies."""
    read_ports = CapitalReaders(
        margin_trading=mock_margin_reader or mocker.Mock(),
        pledge_ratio=mock_pledge_reader or mocker.Mock(),
        valuation_metrics=mock_valuation_reader or mocker.Mock(),
        index_composition=mock_index_reader or mocker.Mock(),
    )
    write_ports = CapitalWriters(
        margin_trading=mocker.Mock(),
        pledge_ratio=mocker.Mock(),
        valuation_metrics=mocker.Mock(),
        index_composition=mocker.Mock(),
    )
    return CapitalStore(read_ports=read_ports, write_ports=write_ports)


@pytest.mark.unit
class TestCapitalStoreIntInstrumentId:
    """Verify CapitalStore get_* methods accept int instrument_id."""

    def test_get_margin_trading_accepts_int_and_passes_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """get_margin_trading should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "trade_date": ["2024-01-01"],
                "margin_buy_balance": [100.0],
            }
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, mock_margin_reader=mock_reader)

        result = service.get_margin_trading(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_get_pledge_ratio_accepts_int_and_passes_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """get_pledge_ratio should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"instrument_id": [2_000_001], "pledge_ratio": [0.5]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, mock_pledge_reader=mock_reader)

        result = service.get_pledge_ratio(
            instrument_id=2_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(2_000_001, date(2024, 1, 1))

    def test_get_valuation_metrics_accepts_int_and_passes_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """get_valuation_metrics should accept int instrument_id and forward it."""
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"instrument_id": [1_000_001], "pe_ratio": [10.5]})
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, mock_valuation_reader=mock_reader)

        result = service.get_valuation_metrics(
            instrument_id=1_000_001, as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1_000_001, date(2024, 1, 1))

    def test_get_index_composition_accepts_str_and_passes_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """get_index_composition should accept str index_id and forward it.

        Index composition uses string index codes (e.g. '399300.XSHE'),
        not int instrument IDs. This is intentional: the index_composition
        table stores index_id as TEXT in the SQLite schema.
        """
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"index_id": ["399300.XSHE"], "instrument_id": [1_000_001]}
        )
        mock_reader.get.return_value = expected_df

        service = _make_service(mocker, mock_index_reader=mock_reader)

        result = service.get_index_composition(
            index_id="399300.XSHE", as_of_date=date(2024, 1, 1)
        )

        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with("399300.XSHE", date(2024, 1, 1))
